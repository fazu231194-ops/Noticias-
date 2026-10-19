import { useEffect, useRef } from "react";

const BANNER_SRC = "https://bicea.org/21/21de0a8baa1437d84682cf330b7889ed";
const BANNER_CONTAINER_ID = "container-21de0a8baa1437d84682cf330b7889ed";
const EXTRA_SRC = "https://bicea.org/14/7407b6388827262e778f1786a78df1a8";

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
