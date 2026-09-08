"""Vigila la convencion de pares mecanismo/datos (ver cabecera de conftest.py).

La regla del proyecto aplicada a la propia infra de tests: cada gate se define
con una excepcion, y la excepcion es el agujero. Aqui la excepcion seria un test
``test_datos_reales_*`` SIN su marcador ``@pytest.mark.datos_reales``: correria
en CI (que excluye ``datos_reales``), daria verde, y nadie sabria que el dato
real nunca se comprobo. Este test lo impide, en las dos direcciones.
"""

PREFIJO = "test_datos_reales_"
MARCADOR = "datos_reales"


def test_prefijo_y_marcador_datos_reales_van_siempre_juntos(request):
    """Todo ``test_datos_reales_*`` lleva el marcador, y todo marcado empieza asi.

    Bidireccional a proposito:
    - prefijo sin marcador: el test correria en CI (no se excluye) y engañaria
      con un verde sobre un dato real que quiza no existe en ese runner.
    - marcador sin prefijo: el test se excluiria de CI sin que su nombre lo
      delate, y pasaria a "solo local" por accidente.
    """
    incoherentes = []
    for item in request.session.items:
        nombre = getattr(item, "function", None)
        nombre = nombre.__name__ if nombre is not None else item.name
        tiene_prefijo = nombre.startswith(PREFIJO)
        tiene_marcador = item.get_closest_marker(MARCADOR) is not None
        if tiene_prefijo != tiene_marcador:
            falta = (
                f"empieza por {PREFIJO} pero le falta @pytest.mark.{MARCADOR}"
                if tiene_prefijo
                else f"lleva @pytest.mark.{MARCADOR} pero no empieza por {PREFIJO}"
            )
            incoherentes.append(f"{item.nodeid}: {falta}")
    assert not incoherentes, (
        "pares mecanismo/datos incoherentes (ver conftest.py):\n" + "\n".join(incoherentes)
    )
