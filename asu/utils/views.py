from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from rest_framework import mixins, serializers, status
from rest_framework.permissions import SAFE_METHODS
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from drf_spectacular.utils import extend_schema_view

from asu.utils.rest import PartialUpdateModelMixin
from asu.utils.typing import UserRequest

if TYPE_CHECKING:
    ViewSetBase = GenericViewSet[Any]
else:
    ViewSetBase = GenericViewSet


_viewset_mixin_map: dict[str, type[Any]] = {
    "list": mixins.ListModelMixin,
    "create": mixins.CreateModelMixin,
    "retrieve": mixins.RetrieveModelMixin,
    "partial_update": PartialUpdateModelMixin,
    "destroy": mixins.DestroyModelMixin,
}


class ViewSetMeta(type):
    def __new__(
        mcs, name: str, bases: tuple[type[Any], ...], classdict: dict[str, Any]
    ) -> type[ViewSetBase]:
        cls_mixins = classdict.get("mixins")

        if cls_mixins is not None:
            for label in cls_mixins:
                try:
                    mixin = _viewset_mixin_map[label]
                except KeyError:
                    raise ValueError(
                        "%s is not a valid mixin name, use one of these: %s"
                        % (label, tuple(_viewset_mixin_map))
                    )

                if mixin in bases:
                    raise TypeError(
                        "mixins.%s already exists or duplicated in '%s'"
                        % (mixin.__name__, name)
                    )

                bases += (mixin,)

        cls = cast(
            type[ViewSetBase],
            super().__new__(mcs, name, bases, classdict),
        )
        schemas = classdict.get("schemas")

        if schemas is not None:
            # Get related action and decorate
            # it with extension e.g. extend_schema.
            cls = extend_schema_view(**schemas)(cls)
        return cls


class ExtendedViewSet(ViewSetBase, metaclass=ViewSetMeta):
    mixins: Sequence[str] | None = None
    schemas: dict[str, Any] | None = None
    serializer_classes: dict[str, Any] = {}
    scopes: dict[str, list[str] | str] = {}
    request: UserRequest

    def get_action_save_response(
        self,
        request: Request,
        serializer: serializers.BaseSerializer[Any]
        | type[serializers.BaseSerializer[Any]]
        | None = None,
        status_code: int = status.HTTP_200_OK,
    ) -> Response:
        # Similar functionality from mixins.CreateModelMixin
        # for ViewSet actions.
        assert status.is_success(status_code)

        if serializer is None:
            serializer = self.get_serializer(data=request.data)
        elif not isinstance(serializer, serializers.BaseSerializer):
            serializer = serializer(
                data=request.data, context=self.get_serializer_context()
            )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        data = serializer.data if status_code != status.HTTP_204_NO_CONTENT else None
        return Response(data, status=status_code)

    def get_serializer_class(self) -> type[serializers.Serializer[Any]]:
        return self.serializer_classes.get(self.action, self.serializer_class)

    @property
    def required_scopes(self) -> list[str]:
        """
        Classify scopes depending on the request method. 'write' for
        unsafe methods and 'read' for safe methods. Used by RequireScope
        permission class.
        """

        # Reference to non-existing action, ignore scopes. Likely to
        # result in 405 Method Not Allowed.
        action = self.action
        if not action:
            return []

        spec = self.scopes[action]
        mode = "read" if self.request.method in SAFE_METHODS else "write"

        if isinstance(spec, str):
            scope = "%s:%s" % (spec, mode)
            return [scope]

        return ["%s:%s" % (scope, mode) for scope in spec]
