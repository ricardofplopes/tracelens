from providers.iqdb import IQDBProvider
from providers.saucenao import SauceNAOProvider
from providers.wikimedia import WikimediaProvider
from providers.google_lens import GoogleLensProvider
from providers.yandex import YandexProvider
from providers.web_search import WebSearchProvider
from providers.social_media import SocialMediaProvider
from providers.tineye import TinEyeProvider
from providers.bing_visual import BingVisualProvider


ALL_PROVIDERS = [
    IQDBProvider(),
    SauceNAOProvider(),
    WikimediaProvider(),
    GoogleLensProvider(),
    YandexProvider(),
    WebSearchProvider(),
    SocialMediaProvider(),
    TinEyeProvider(),
    BingVisualProvider(),
]


def get_all_providers(settings=None):
    """Return list of all provider instances."""
    return ALL_PROVIDERS


def get_enabled_providers(settings):
    """Return only providers that are enabled in settings."""
    return [p for p in ALL_PROVIDERS if p.enabled(settings)]
