import { Link } from "@tanstack/react-router";

export function Masthead() {
  const today = new Date().toLocaleDateString("es-AR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return (
    <header className="border-b-4 border-double border-foreground">
      <div className="mx-auto max-w-6xl px-4 py-2 text-xs uppercase tracking-widest text-muted-foreground flex justify-between">
        <span>{today}</span>
        <span className="hidden sm:inline">Edición digital</span>
      </div>
      <div className="mx-auto max-w-6xl px-4 pb-4 text-center">
        <Link to="/" className="font-display text-4xl sm:text-6xl font-black tracking-tight">
          Panorama Global News
        </Link>
        <p className="mt-1 text-sm italic text-muted-foreground">Noticias automatizadas, al instante</p>
      </div>
    </header>
  );
}
