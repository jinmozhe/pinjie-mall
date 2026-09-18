import ipaddress


def masked_ip(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{address}/24", strict=False))
    return str(ipaddress.ip_network(f"{address}/64", strict=False))


__all__ = ["masked_ip"]
