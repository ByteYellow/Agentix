"""`Dispatcher` — a namespace's collection of bound (stub, impl) pairs.

Namespaces construct one of these implicitly via `bind_namespace(target)`;
explicit `bind(stub, impl)` is for namespaces using the composition-impl
shape (separate stub class + impl class, see CLAUDE.md R1).

`dispatch` / `dispatch_stream` / `dispatch_bidi` coerce wire-decoded args
back into the declared types, invoke the impl, and trap exceptions into
RemoteError so the wire stays 200.
"""

from __future__ import annotations

import inspect
import logging
import traceback
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, ParamSpec, TypeVar, get_args

from pydantic import TypeAdapter, ValidationError

import agentix.trace as trace
from agentix.dispatch.bound import _BoundMethod, coerce_args, source_for
from agentix.dispatch.shape import detect_shape
from agentix.idents import MethodName
from agentix.namespace import discover_methods
from agentix.rpc import is_channel_annotation
from agentix.runtime.shared.models import (
    RemoteError,
    RemoteRequest,
    RemoteResponse,
)

logger = logging.getLogger("agentix.dispatch")

P = ParamSpec("P")
R = TypeVar("R")


class Dispatcher:
    """A namespace's collection of bound (stub, impl) pairs.

    Namespaces construct one of these in their `_register.register()`:

        from agentix.dispatch import Dispatcher
        from . import run               # the stub (Ellipsis body)
        from ._impl import run as _run  # the real impl

        def register() -> Dispatcher:
            d = Dispatcher()
            d.bind(run, _run)
            return d
    """

    def __init__(self) -> None:
        self._methods: dict[MethodName, _BoundMethod[Any, Any]] = {}

    def bind(
        self,
        stub: Callable[P, R],
        impl: Callable[..., R | Awaitable[R]],
    ) -> None:
        """Register `impl` as the implementation of `stub`.

        Both must share the same signature (the stub is just the typed
        contract; impl carries the body). The wire request's `method`
        field is `stub.__name__`. The call shape is detected from the
        signature at bind time and cached.
        """
        # eval_str=True resolves PEP 563 stringified annotations (`from
        # __future__ import annotations` in the stub module) — without it,
        # `param.annotation` would be the string "AsyncIterator[Foo]" and
        # `get_origin` would return None, mis-classifying streams as unary.
        sig = inspect.signature(stub, eval_str=True)
        name = MethodName(stub.__name__)
        if name in self._methods:
            raise ValueError(f"method '{name}' already bound on this dispatcher")
        shape = detect_shape(stub, sig)

        param_adapters: dict[str, TypeAdapter[Any]] = {}
        channel_params: list[tuple[str, Any]] = []
        for pname, param in sig.parameters.items():
            ann = param.annotation if param.annotation is not inspect.Parameter.empty else Any
            if is_channel_annotation(ann):
                # Channel[T] params: adapter validates items, not the channel itself.
                args = get_args(ann)
                item_type = args[0] if args else Any
                channel_params.append((pname, item_type))
                param_adapters[pname] = TypeAdapter(item_type)
            else:
                param_adapters[pname] = TypeAdapter(ann)

        return_ann = sig.return_annotation if sig.return_annotation is not inspect.Signature.empty else Any
        item_adapter: TypeAdapter[Any] | None = None
        input_channel_param: str | None = None
        input_item_adapter: TypeAdapter[Any] | None = None
        if shape == "unary":
            return_adapter = TypeAdapter(return_ann)
        else:
            # Stream + bidi both serialise items via the return type's T.
            args = get_args(return_ann)
            item_type = args[0] if args else Any
            item_adapter = TypeAdapter(item_type)
            return_adapter = TypeAdapter(Any)  # unused on streaming path
            if shape == "bidi":
                input_channel_param, input_item_type = channel_params[0]
                input_item_adapter = TypeAdapter(input_item_type)

        self._methods[name] = _BoundMethod(
            name=name,
            stub=stub,
            impl=impl,
            signature=sig,
            shape=shape,
            param_adapters=param_adapters,
            return_adapter=return_adapter,
            item_adapter=item_adapter,
            input_channel_param=input_channel_param,
            input_item_adapter=input_item_adapter,
        )

    def bind_namespace(self, target: Any) -> Dispatcher:
        """Bind every public async function on `target`.

        `target` is whatever the namespace's entry point points at —
        typically a Python module (the package itself), or a class for
        legacy class-style namespaces, or any object with discoverable
        async attributes. The dispatcher binds each function to itself
        (stub and impl are the same callable).

        Returns `self` for fluent use in entry-point loaders.
        """
        for _name, fn in discover_methods(target):
            self.bind(fn, fn)
        return self

    def methods(self) -> list[MethodName]:
        return list(self._methods)

    def is_streaming(self, method: MethodName) -> bool:
        m = self._methods.get(method)
        return m is not None and m.is_stream

    def is_bidi(self, method: MethodName) -> bool:
        m = self._methods.get(method)
        return m is not None and m.is_bidi

    def input_adapter_for(self, method: MethodName) -> TypeAdapter[Any] | None:
        m = self._methods.get(method)
        return m.input_item_adapter if m else None

    async def dispatch(self, request: RemoteRequest) -> RemoteResponse:
        """Route a RemoteRequest to its bound impl, returning the wire response.

        Validates kwargs against the stub's signature, awaits async impls,
        serializes the return via the stub's return-type adapter, and
        traps exceptions into a RemoteError so the wire stays 200.
        """
        m = self._methods.get(request.method)
        if m is None:
            return RemoteResponse(
                ok=False,
                error=RemoteError(
                    type="MethodNotFound",
                    message=f"method '{request.method}' is not bound on this dispatcher; "
                    f"available: {sorted(self._methods)}",
                ),
            )
        try:
            args, kwargs = coerce_args(m, request.args, request.kwargs)
        except ValidationError as exc:
            return RemoteResponse(
                ok=False,
                error=RemoteError(type="ValidationError", message=str(exc)),
            )
        tokens = trace.set_call_context(request.call_id, source_for(m.impl))
        try:
            try:
                result = m.impl(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
            except Exception as exc:
                logger.exception("namespace impl '%s' raised", m.name)
                return RemoteResponse(
                    ok=False,
                    error=RemoteError(
                        type=type(exc).__name__,
                        message=str(exc),
                        traceback=traceback.format_exc(),
                    ),
                )
        finally:
            trace.reset_call_context(tokens)
        try:
            value = m.return_adapter.dump_python(result, mode="python")
        except Exception as exc:
            return RemoteResponse(
                ok=False,
                error=RemoteError(
                    type="SerializationError",
                    message=f"failed to serialize return value: {exc}",
                ),
            )
        return RemoteResponse(ok=True, value=value)

    async def dispatch_stream(self, request: RemoteRequest) -> AsyncIterator[dict[str, Any]]:
        """Run a server-streaming impl, yielding event dicts to the transport.

        Event shapes:
            {"item": <serialized>}      — per yielded value
            {"error": {...}}            — impl raised, validation failed, etc.
            {"end": true}               — normal completion sentinel

        The transport (Socket.IO server / HTTP NDJSON) encodes the dicts to
        the wire. The dispatcher only deals with semantic events.
        """
        m = self._methods.get(request.method)
        if m is None:
            yield {"type": "error", "error": RemoteError(
                type="MethodNotFound",
                message=f"method '{request.method}' is not bound on this dispatcher; "
                f"available: {sorted(self._methods)}",
            ).model_dump()}
            return
        if not m.is_stream or m.is_bidi:
            yield {"type": "error", "error": RemoteError(
                type="NotAStreamingMethod",
                message=f"method '{request.method}' is not a (non-bidi) streaming method",
            ).model_dump()}
            return
        try:
            args, kwargs = coerce_args(m, request.args, request.kwargs)
        except ValidationError as exc:
            yield {"type": "error", "error": RemoteError(type="ValidationError", message=str(exc)).model_dump()}
            return
        tokens = trace.set_call_context(request.call_id, source_for(m.impl))
        try:
            try:
                result = m.impl(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                assert m.item_adapter is not None
                async for item in result:
                    try:
                        value = m.item_adapter.dump_python(item, mode="python")
                    except Exception as exc:
                        yield {"type": "error", "error": RemoteError(
                            type="SerializationError",
                            message=f"failed to serialize item: {exc}",
                        ).model_dump()}
                        return
                    yield {"type": "item", "value": value}
            except Exception as exc:
                logger.exception("namespace stream impl '%s' raised mid-stream", m.name)
                yield {"type": "error", "error": RemoteError(
                    type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                ).model_dump()}
                return
        finally:
            trace.reset_call_context(tokens)
        yield {"type": "end"}

    async def dispatch_bidi(
        self,
        request: RemoteRequest,
        input_iter: AsyncIterator[Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Run a bidi impl. `input_iter` yields items already coerced to the
        stub's input item type (transport pre-validates via `input_item_adapter`).

        Event shapes match `dispatch_stream` — same vocab of `item` / `end`
        / `error` — so the transport handles them uniformly.
        """
        m = self._methods.get(request.method)
        if m is None:
            yield {"type": "error", "error": RemoteError(
                type="MethodNotFound",
                message=f"method '{request.method}' is not bound on this dispatcher; "
                f"available: {sorted(self._methods)}",
            ).model_dump()}
            return
        if not m.is_bidi:
            yield {"type": "error", "error": RemoteError(
                type="NotABidiMethod",
                message=f"method '{request.method}' is not bidirectional",
            ).model_dump()}
            return
        assert m.input_channel_param is not None
        # Bind non-channel args/kwargs; inject input_iter as the channel param.
        non_channel_kwargs = dict(request.kwargs)
        non_channel_kwargs.pop(m.input_channel_param, None)
        try:
            bound = m.signature.bind_partial(*request.args, **non_channel_kwargs)
            bound.apply_defaults()
            coerced: dict[str, Any] = {}
            for pname, raw in bound.arguments.items():
                if pname == m.input_channel_param:
                    continue
                adapter = m.param_adapters.get(pname)
                coerced[pname] = adapter.validate_python(raw) if adapter is not None else raw
            coerced[m.input_channel_param] = input_iter
        except (TypeError, ValidationError) as exc:
            yield {"type": "error", "error": RemoteError(type=type(exc).__name__, message=str(exc)).model_dump()}
            return
        tokens = trace.set_call_context(request.call_id, source_for(m.impl))
        try:
            try:
                result = m.impl(**coerced)
                if inspect.isawaitable(result):
                    result = await result
                assert m.item_adapter is not None
                async for item in result:
                    try:
                        value = m.item_adapter.dump_python(item, mode="python")
                    except Exception as exc:
                        yield {"type": "error", "error": RemoteError(
                            type="SerializationError",
                            message=f"failed to serialize item: {exc}",
                        ).model_dump()}
                        return
                    yield {"type": "item", "value": value}
            except Exception as exc:
                logger.exception("namespace bidi impl '%s' raised mid-stream", m.name)
                yield {"type": "error", "error": RemoteError(
                    type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                ).model_dump()}
                return
        finally:
            trace.reset_call_context(tokens)
        yield {"type": "end"}


__all__ = ["Dispatcher"]
