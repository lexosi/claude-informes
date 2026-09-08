# NO PUBLICAR hasta limpiar el historial

**Este repositorio NO debe hacerse publico tal cual.** La punta actual esta
limpia, pero el **historial de git** contiene datos reales del autor. Hacerlo
publico ahora los expone; quitarlos en un commit nuevo **no los borra del
historial**, que es justo el error que este fichero existe para evitar.

Hoy el repo es **privado** en su remoto, asi que no hay fuga externa. El riesgo
se materializa el dia que se ponga en publico. Este es el ultimo paso antes de
publicar, no antes.

## Que contiene el historial (categorias, no verbatim)

Se describen por categoria a proposito: reproducir los valores aqui volveria a
filtrarlos en la punta.

1. **Nombre de usuario de Windows real** — de dos maquinas distintas del autor.
2. **Rutas absolutas reales** — letra de disco + carpeta raiz de proyectos del
   autor, y la raiz del archivo de informes.
3. **`config/proyectos.json` REAL commiteado** — la lista blanca de verdad, con
   las rutas de los proyectos del autor. Es el dato mas sensible: no es una
   fixture, es la configuracion real. Ya no existe en la punta (se quito), pero
   sigue en el historial.
4. **Nombres reales de otros proyectos del autor** — en docstrings, README y
   fixtures de las versiones antiguas.

## En que commits

- **Datos de la maquina antigua** (usuario, `config/proyectos.json` real, rutas
  absolutas): los **6 commits publicados**, `811481e` .. `c3044d5`.
- **Usuario de la maquina actual y nombres de proyecto reales**: presentes en el
  arbol hasta `1d314bd` inclusive.
- **Primer commit con el arbol ya limpio**: `c0fb708` (el que arreglo el guard y
  scrubeo las fixtures). De ahi en adelante la punta esta limpia.

En resumen: hay que reescribir **todo lo anterior a `c0fb708`**. Los hashes
pueden desplazarse segun caigan commits nuevos; el invariante estable es *"todo
lo previo al primer commit de arbol limpio"*.

## Que hacer antes de publicar

| Opcion | Que hace | Coste |
| --- | --- | --- |
| `git filter-repo` (o BFG) + `push --force` | Reescribe todos los commits y borra los blobs con datos reales | Cambia todos los hashes; reescribe historia; irreversible en el remoto |
| Recrear el repo desde un arbol limpio | Historial nuevo (p. ej. un squash desde `c0fb708`) | Se pierde el historial de commits como narrativa del proceso |

La decision es del autor. No la tome un agente por su cuenta.

## Como comprobar que quedo limpio

Debe dar **cero** en todo el historial, no solo en HEAD:

```sh
# ningun identificador real, en ninguna forma, en ningun commit
git log -S "<usuario>"    --all --oneline
git log -S "<raiz-real>"  --all --oneline
git log --all -- config/proyectos.json   # no debe existir en ningun commit
```

Y el guard `tests/test_publicable.py` debe pasar sobre el arbol de **cada**
commit que sobreviva, no solo sobre la punta.

## Estado

- Repo remoto: **privado** a fecha de este fichero.
- Punta (`HEAD`): limpia — lo verifica `tests/test_publicable.py`.
- Historial: **sucio** — pendiente de reescritura antes de publicar.
