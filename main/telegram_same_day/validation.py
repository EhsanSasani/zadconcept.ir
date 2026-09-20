"""Validate the consumed subset before any database or network operation."""


class InvalidUpdate(ValueError):
    pass


def integer(value, *, positive=False):
    if type(value) is not int or abs(value) > 2**63 - 1:
        raise InvalidUpdate("invalid_integer")
    if positive and value <= 0:
        raise InvalidUpdate("invalid_positive_integer")
    return value


def validate_message(message, *, nested=False):
    if not isinstance(message, dict) or not isinstance(message.get("chat"), dict):
        raise InvalidUpdate("invalid_message")
    integer(message.get("message_id"), positive=True)
    integer(message["chat"].get("id"))
    if message["chat"].get("type") not in {"channel", "group", "supergroup", "private"}:
        raise InvalidUpdate("invalid_chat_type")
    for key in ("date", "edit_date"):
        if key in message:
            integer(message[key], positive=True)
            if message[key] > 253402300799:
                raise InvalidUpdate("invalid_date")
    for key in ("text", "caption"):
        if key in message and (not isinstance(message[key], str) or len(message[key]) > 4096):
            raise InvalidUpdate("invalid_text")
    for key in ("from", "sender_chat"):
        if key in message:
            if not isinstance(message[key], dict):
                raise InvalidUpdate("invalid_sender")
            integer(message[key].get("id"))
    if "photo" in message:
        photos = message["photo"]
        if not isinstance(photos, list) or not 1 <= len(photos) <= 20:
            raise InvalidUpdate("invalid_photos")
        for photo in photos:
            if not isinstance(photo, dict) or not isinstance(photo.get("file_id"), str):
                raise InvalidUpdate("invalid_photo")
            if not 1 <= len(photo["file_id"]) <= 512:
                raise InvalidUpdate("invalid_file_id")
            integer(photo.get("width"), positive=True)
            integer(photo.get("height"), positive=True)
    if "forward_origin" in message:
        origin = message["forward_origin"]
        if not isinstance(origin, dict):
            raise InvalidUpdate("invalid_origin")
        if origin.get("type") == "channel":
            if not isinstance(origin.get("chat"), dict):
                raise InvalidUpdate("invalid_origin_chat")
            integer(origin["chat"].get("id"))
            integer(origin.get("message_id"), positive=True)
    if "message_thread_id" in message:
        integer(message["message_thread_id"], positive=True)
    if "reply_to_message" in message:
        if nested:
            raise InvalidUpdate("nested_reply")
        validate_message(message["reply_to_message"], nested=True)


def validate_update(update):
    if not isinstance(update, dict):
        raise InvalidUpdate("invalid_update")
    integer(update.get("update_id"))
    if update["update_id"] < 0:
        raise InvalidUpdate("invalid_update_id")
    keys = [key for key in ("channel_post", "edited_channel_post", "message", "edited_message") if key in update]
    if len(keys) > 1:
        raise InvalidUpdate("multiple_messages")
    if not keys:
        return None, None
    key = keys[0]
    validate_message(update[key])
    return key, update[key]
