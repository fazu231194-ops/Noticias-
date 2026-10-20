import { useEffect, useRef } from "react";

const BANNER_SRC = "https://bicea.org/21/fe8dc58d1842344ff43260addfa91f0a";
const BANNER_CONTAINER_ID = "container-fe8dc58d1842344ff43260addfa91f0a";
const EXTRA_SRC = "https://bicea.org/14/14c4ff326d0c794d7937b57fdb418c2f";

function addScript(src: string, async: boolean) {
  if (document.querySelector(`script[src="${src}"]`)) return;
  const s = document.createElement("script");
  s.src = src;
  s.async = async;
  s.setAttribute("data-cfasync", "false");
  document.body.appendChild(s);
}

/** Banner nativo: el script rellena el div con id `container-...`. */
export function AdBanner() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Un solo contenedor con este id por página; el script lo busca por id.
    // Al navegar entre páginas se vuelve a insertar el script para que rellene el nuevo contenedor.
    document.querySelectorAll(`script[src="${BANNER_SRC}"]`).forEach((el) => el.remove());
    if (ref.current) addScript(BANNER_SRC, true);
  }, []);
  return (
    <div className="my-8 flex justify-center">
      <div ref={ref} id={BANNER_CONTAINER_ID} />
    </div>
  );
}

/** Segundo script de la red (se carga una sola vez en toda la web). */
export function AdScripts() {
  useEffect(() => {
    addScript(EXTRA_SRC, false);
  }, []);
  return null;
}
