from pydantic import model_serializer


class MidasDocument:
    """Mixin that renames MongoDB _id → id in JSON output."""

    @model_serializer(mode="wrap")
    def _ser(self, serializer, info):
        data = serializer(self)
        if "_id" in data:
            data["id"] = str(data.pop("_id"))
        return data
