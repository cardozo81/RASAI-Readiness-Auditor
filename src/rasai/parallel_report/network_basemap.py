"""Offline world basemap for unlocated network observations.

The geometry is contextual cartography (Natural Earth) and deliberately does
not imply any measured IP position, topology, geolocation or route. The source
of truth for markers is a verified GeoIP coordinate carried by AUD evidence.
"""
from html import escape

from rasai.network_world_land import WORLD_LAND_SVG_PATH


def unlocated_world_map(*, observed_public_peers: int = 0) -> str:
    """Provide visual context with zero fabricated map points."""
    amount = max(0, observed_public_peers) if type(observed_public_peers) is int else 0
    lines = []
    for lon in range(-180, 181, 60):
        x = 40 + (lon + 180) / 360 * 800
        lines.append(f"<line x1='{x:.2f}' y1='20' x2='{x:.2f}' y2='380' stroke='#d6e2ec'/>")
        lines.append(f"<text x='{x:.2f}' y='402' text-anchor='middle' font-size='12' fill='#3e5160'>{lon}°</text>")
    for lat in range(-90, 91, 30):
        y = 20 + (90 - lat) / 180 * 360
        lines.append(f"<line x1='40' y1='{y:.2f}' x2='840' y2='{y:.2f}' stroke='#d6e2ec'/>")
        lines.append(f"<text x='30' y='{y+4:.2f}' text-anchor='end' font-size='12' fill='#3e5160'>{lat}°</text>")
    note = (
        f"IP público do servidor remoto observado em {amount} captura(s) passiva(s). "
        "Nenhuma coordenada GeoIP verificável foi persistida para posicioná-lo. "
        "IP de servidor observado não identifica o IP de origem do usuário nem "
        "comprova localização física, datacenter ou caminho de rede."
        if amount else
        "Nenhum IP público com geolocalização verificável foi persistido. "
        "Nenhum ponto representa uma medição."
    )
    return (
        '<section class="panel" id="network-map" data-map-state="unlocated">'
        '<h2>Mapa geográfico consultivo</h2>'
        '<p class="callout w">Localização não determinada. A cartografia mundial '
        'é exibida para contexto, não como resultado de medição. '
        'Sem coordenadas verificadas, nenhum marcador ou trajeto é desenhado.</p>'
        '<div class="table-wrap"><svg class="network-map-plot" '
        'viewBox="0 0 880 430" role="img" '
        'aria-label="Mapa-múndi de referência sem pontos de rede localizados">'
        '<title>Mapa-múndi sem geolocalização comprovada</title>'
        '<desc>Mapa base de contexto; não há marcadores de localização, '
        'saltos de traceroute nem linhas de rota.</desc>'
        "<path data-map-layer='land' d='" + WORLD_LAND_SVG_PATH +
        "' fill='#e1eee7' stroke='#91a7a0' stroke-width='0.7'/>"
        + ''.join(lines) +
        '</svg></div><p class="rf">' + escape(note) + '</p>'
        '<p class="rf">Mapa base Natural Earth 1:110 milhões, cartografia de domínio '
        'público; não representa infraestrutura auditada. Para localizar um '
        'IP por ponto aproximado, é necessário enriquecimento GeoIP com fonte, '
        'precisão e coordenadas persistidas e verificáveis.</p></section>'
    )
