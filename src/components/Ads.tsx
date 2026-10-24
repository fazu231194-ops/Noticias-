import { useEffect } from "react";

// Pegá acá tu código de AdSense cuando lo tengas (client ID y slot del anuncio)
// Mientras tanto, estos componentes no muestran nada.

/** Espacio reservado para un bloque de anuncios de AdSense. */
export function AdBanner() {
  return (
    <div className="my-8 flex justify-center">
      {/* TODO: reemplazar por el <ins className="adsbygoogle" ...> de AdSense */}
    </div>
  );
}

/** Script global de AdSense (se carga una sola vez en toda la web). */
export function AdScripts() {
  useEffect(() => {
    // TODO: acá va <script async src="https://pagead2.googlesyndication.com/..."> cuando actives AdSense
  }, []);
  return null;
}
