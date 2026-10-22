import { createFileRoute, Link } from "@tanstack/react-router";
import { Masthead } from "@/components/Masthead";

const EMAIL = "fazroman2012@gmail.com";

export const Route = createFileRoute("/contacto")({
  head: () => ({
    meta: [
      { title: "Contacto — Panorama Global News" },
      {
        name: "description",
        content: "Escribinos para reportar un error, enviar una consulta o pedir la corrección de una nota.",
      },
    ],
  }),
  component: Contact,
});

function Contact() {
  return (
    <div className="min-h-screen">
      <Masthead />
      <main className="mx-auto max-w-xl px-4 py-8">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">← Volver a portada</Link>
        <h1 className="mt-6 font-display text-3xl sm:text-5xl font-black leading-tight">Contacto</h1>

        <div className="mt-6 space-y-5 text-lg leading-relaxed">
          <p>
            Para consultas, para reportar un error o para pedir la corrección o el retiro de
            una nota, escribinos por correo electrónico.
          </p>
          <p>
            <a
              href={`mailto:${EMAIL}`}
              className="font-semibold underline underline-offset-4"
            >
              {EMAIL}
            </a>
          </p>
          <p className="text-base text-muted-foreground">
            Si el mensaje se refiere a una nota en particular, incluí el enlace para poder
            revisarla más rápido.
          </p>
        </div>
      </main>
    </div>
  );
}
