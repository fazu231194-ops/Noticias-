import { createFileRoute, Link } from "@tanstack/react-router";
import { Masthead } from "@/components/Masthead";

export const Route = createFileRoute("/quienes-somos")({
  head: () => ({
    meta: [
      { title: "Quiénes somos — Panorama Global News" },
      {
        name: "description",
        content:
          "Panorama Global News es un portal de noticias automatizado que resume y reescribe en español noticias de distintos medios, con enlace a la fuente original.",
      },
    ],
  }),
  component: About,
});

function About() {
  return (
    <div className="min-h-screen">
      <Masthead />
      <main className="mx-auto max-w-3xl px-4 py-8">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">← Volver a portada</Link>
        <h1 className="mt-6 font-display text-3xl sm:text-5xl font-black leading-tight">Quiénes somos</h1>

        <div className="mt-6 space-y-5 text-lg leading-relaxed">
          <p>
            Panorama Global News es un portal de noticias automatizado. Su objetivo es
            ofrecer, en español y en un solo lugar, un panorama de lo que publican medios de
            Argentina, México, Estados Unidos y otros países.
          </p>

          <h2 className="pt-2 font-display text-2xl font-bold">Cómo funciona</h2>
          <p>
            Varias veces por día, un sistema automático revisa los canales de noticias
            (RSS) de distintos medios, selecciona las notas más recientes y utiliza
            inteligencia artificial para redactar una versión propia en español. Cada
            nota incluye el enlace a la fuente original, donde se puede leer la
            información completa.
          </p>

          <h2 className="pt-2 font-display text-2xl font-bold">Uso de inteligencia artificial</h2>
          <p>
            Los textos de este sitio son generados con ayuda de inteligencia artificial a
            partir de información publicada por otros medios. Aunque se intenta mantener la
            fidelidad a la fuente, pueden contener errores u omisiones. Ante cualquier
            duda, recomendamos consultar la nota original.
          </p>

          <h2 className="pt-2 font-display text-2xl font-bold">Errores y correcciones</h2>
          <p>
            Si encontrás un error o querés que revisemos una nota, escribinos desde la
            página de{" "}
            <Link to="/contacto" className="font-semibold underline underline-offset-4">contacto</Link>
            . Corregimos o retiramos el contenido que lo requiera.
          </p>
        </div>
      </main>
    </div>
  );
}
