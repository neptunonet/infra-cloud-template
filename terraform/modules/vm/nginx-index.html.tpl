<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title} · ${name}</title>
<style>
  :root { --bg1:#0b1f3a; --bg2:#1e4e8c; --ink:#14203a; --muted:#5b6678; --ok:#127a4d; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; display:grid; place-items:center; padding:24px;
         font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; color:var(--ink);
         background:linear-gradient(135deg,var(--bg1),var(--bg2)); }
  main { width:100%; max-width:720px; background:#fff; border-radius:20px; overflow:hidden;
         box-shadow:0 20px 60px rgba(0,0,0,.35); }
  header { padding:32px 36px 24px; border-bottom:1px solid #e6ebf2; }
  .badge { display:inline-block; font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
           color:#fff; background:var(--ok); padding:4px 10px; border-radius:999px; }
  h1 { margin:14px 0 6px; font-size:30px; line-height:1.2; }
  header p { margin:0; color:var(--muted); }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:1px; background:#e6ebf2; }
  .cell { background:#f7f9fc; padding:16px 20px; }
  .cell small { display:block; font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
  .cell b { font:600 15px ui-monospace,SFMono-Regular,Menlo,monospace; word-break:break-all; }
  footer { padding:20px 36px 28px; }
  footer p { margin:0 0 8px; }
  code { font:14px ui-monospace,SFMono-Regular,Menlo,monospace; background:#eef3fb; padding:2px 6px; border-radius:5px; }
</style>
</head>
<body>
<main>
  <header>
    <span class="badge">Creado con OpenTofu</span>
    <h1>${title}</h1>
    <p>Esta página la escribió el script de arranque del módulo <code>vm</code> (nginx creado con OpenTofu), no una persona por SSH.</p>
  </header>
  <section class="grid">
    <div class="cell"><small>VM</small><b>${name}</b></div>
    <div class="cell"><small>Zona</small><b>${zone}</b></div>
    <div class="cell"><small>Entorno</small><b>${environment}</b></div>
    <div class="cell"><small>Gestionada por</small><b>opentofu</b></div>
  </section>
  <footer>
    <p><b>Probá:</b> <code>tofu destroy</code> y después <code>tofu apply</code>. La VM vuelve y esta página vuelve idéntica, porque está en el código.</p>
    <p>Cambiar este texto es cambiar código: <code>nginx_title</code> en el <code>.tfvars</code>, <code>plan</code> y <code>apply</code>.</p>
  </footer>
</main>
</body>
</html>
