def get_provider_priorities(settings) -> dict[str, int]:
    """Parse provider priority string into dict."""
    priorities = {}
    for item in settings.PROVIDER_PRIORITIES.split(","):
        item = item.strip()
        if ":" in item:
            name, priority = item.rsplit(":", 1)
            try:
                priorities[name.strip()] = int(priority.strip())
            except ValueError:
                continue
    return priorities


def get_confidence_weight(provider_name: str, priorities: dict[str, int]) -> float:
    """Get confidence multiplier based on provider priority."""
    priority = priorities.get(provider_name, 5)
    # Scale: priority 10 = 1.2x weight, priority 5 = 1.0x, priority 1 = 0.8x
    return 0.8 + (priority - 1) * (0.4 / 9)
