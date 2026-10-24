import { useEffect } from "react";

const ADSENSE_CLIENT = "ca-pub-8492415020519883";
const ADSENSE_SRC = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${ADSENSE_CLIENT}`;

function addScript(src: string) {
  if (document.querySelector(`script[src="${src}"]`)) return;
  const s = document.createElement("script");
  s.src = src;
  s.async = true;
  s.crossOrigin = "anonymous";
  document.head.appendChild(s);
}

/**
 * Con los anuncios automáticos activados en AdSense, Google decide
 * dónde insertar los anuncios en cada página. No hace falta reservar
 * un espacio manual, así que este componente no renderiza nada visible.
 */
export function AdBanner() {
  return null;
}

/** Carga el script de AdSense una sola vez en toda la web. */
export function AdScripts() {
  useEffect(() => {
    addScript(ADSENSE_SRC);
  }, []);
  return null;
}
