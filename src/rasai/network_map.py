"""#659 G3: offline consultative coordinate plot, not a physical network route."""
from __future__ import annotations

from html import escape
from math import isfinite
from typing import Any


def _coordinate(value: Any, lower: float, upper: float) -> float | None:
    if type(value) not in (int, float):
        return None
    number = float(value)
    return number if isfinite(number) and lower <= number <= upper else None


def network_geographic_panel(probes: list[dict]) -> str:
    """Render only approximate positions explicitly supplied by verified sidecars.

    No geographic paths/lines are inferred. A grid without coordinates is not
    a map of measured infrastructure, so absent enrichment has a logical fallback.
    """
    markers = []
    for probe in probes[:32]:
        measurements = probe.get("metrics")
        if not isinstance(measurements, dict):
            continue
        geo = measurements.get("geoip")
        if not isinstance(geo, dict) or geo.get("state") != "OBSERVED":
            continue
        value = geo.get("value")
        if not isinstance(value, dict):
            continue
        lat = _coordinate(value.get("latitude"), -90, 90)
        lon = _coordinate(value.get("longitude"), -180, 180)
        radius = _coordinate(value.get("accuracy_radius_km"), 0, 20000)
        if lat is None or lon is None or radius is None:
            continue
        name = str(probe.get("hostname") or "Destino público")
        origin = str(value.get("source") or "Base geográfica local")
        capture = str(probe.get("capture_utc") or "Data não comprovada")
        desc = (f"{name}. Posição estimada em {lat:.3f}°, {lon:.3f}°. "
                f"Precisão declarada: raio de {radius:g} km. "
                f"Fonte: {origin}. Coleta: {capture}. "
                "Posição estimada da referência IP, não do servidor físico.")
        # Equirectangular projection; fixed mathematical axes without remote map tiles.
        x, y = 40 + (lon + 180) / 360 * 800, 20 + (90 - lat) / 180 * 360
        markers.append(
            f"<circle cx='{x:.2f}' cy='{y:.2f}' r='7' fill='#24578b' "
            f"stroke='#ffffff' stroke-width='2'><title>{escape(desc)}</title></circle>"
        )
    if not markers:
        return (
            "<section class='panel'><h2>Mapa e caminho de rede</h2>"
            "<p>Não há coordenadas geográficas sustentadas por uma fonte persistida. "
            "Por isso, nenhum ponto ou trajeto físico é desenhado. "
            "O destino observado, a resolução de nomes e as conexões "
            "estão detalhados nas tabelas de rede, quando disponíveis.</p>"
            "</section>"
        )
    grid = []
    for lon in range(-180, 181, 60):
        x = 40 + (lon + 180) / 360 * 800
        grid.append(f"<line x1='{x:.2f}' y1='20' x2='{x:.2f}' y2='380' stroke='#d6e2ec'/>")
        grid.append(f"<text x='{x:.2f}' y='402' text-anchor='middle' font-size='12' fill='#3e5160'>{lon}°</text>")
    for lat in range(-90, 91, 30):
        y = 20 + (90 - lat) / 180 * 360
        grid.append(f"<line x1='40' y1='{y:.2f}' x2='840' y2='{y:.2f}' stroke='#d6e2ec'/>")
        grid.append(f"<text x='30' y='{y+4:.2f}' text-anchor='end' font-size='12' fill='#3e5160'>{lat}°</text>")
    return (
        "<section class='panel'><h2>Mapa geográfico consultivo</h2>"
        "<p>Pontos são estimativas geográficas da referência IP, "
        "com precisão limitada pela base local; não representam necessariamente "
        "a sede, o centro de dados, a rota percorrida ou a posição de um usuário. "
        "Não são desenhadas ligações físicas sem medição correspondente.</p>"
        "<div class='table-wrap'><svg viewBox='0 0 880 430' role='img' "
        "aria-label='Representação aproximada de locais com coordenadas documentadas' "
        "style='display:block;min-width:550px;max-width:100%;background:#f2f7fb'>"
        + "".join(grid) + "".join(markers) + "</svg></div>"
        "<p>Escala por latitude e longitude; passe o cursor ou navegue até "
        "os marcadores para consultar a fonte, o horário e a precisão estimada.</p>"
        "</section>"
    )
