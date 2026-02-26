from typing import Annotated

from fastapi import Depends

from .config import Settings, settings


def get_settings() -> Settings:
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]
