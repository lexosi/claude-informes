"""Watches the mechanism/real-data pair convention (see the header of conftest.py).

The project's rule applied to the test infrastructure itself: every gate is
defined with an exception, and the exception is the hole. Here the exception
would be a ``test_real_data_*`` test WITHOUT its ``@pytest.mark.real_data``
marker: it would run in CI (which excludes ``real_data``), come out green, and
nobody would know the real data was never checked. This test prevents that, in
both directions.
"""

PREFIJO = "test_real_data_"
MARCADOR = "real_data"


def test_the_real_data_prefix_and_marker_always_go_together(request):
    """Every ``test_real_data_*`` carries the marker, and every marked test starts so.

    Bidirectional on purpose:
    - prefix without marker: the test would run in CI (it is not excluded) and
      mislead with a green over real data that may not exist on that runner.
    - marker without prefix: the test would be excluded from CI without its name
      giving it away, and would silently become "local only".
    """
    incoherentes = []
    for item in request.session.items:
        nombre = getattr(item, "function", None)
        nombre = nombre.__name__ if nombre is not None else item.name
        tiene_prefijo = nombre.startswith(PREFIJO)
        tiene_marcador = item.get_closest_marker(MARCADOR) is not None
        if tiene_prefijo != tiene_marcador:
            falta = (
                f"starts with {PREFIJO} but is missing @pytest.mark.{MARCADOR}"
                if tiene_prefijo
                else f"carries @pytest.mark.{MARCADOR} but does not start with {PREFIJO}"
            )
            incoherentes.append(f"{item.nodeid}: {falta}")
    assert not incoherentes, (
        "inconsistent mechanism/real-data pairs (see conftest.py):\n" + "\n".join(incoherentes)
    )
