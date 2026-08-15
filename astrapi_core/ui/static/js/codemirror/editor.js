// astrapi_core/ui/static/js/codemirror/editor.js
//
// Duenne Glue-Schicht um das vendorierte CodeMirror 5 (siehe SOURCES.txt).
// Kein Modul-System noetig -- alle CodeMirror-Dateien haengen sich an das
// globale window.CodeMirror. Diese Datei selbst wird als normales <script>
// eingebunden (nicht als ES-Modul), definiert nur window.mountCodeEditor().
//
// Verwendung (siehe file_editor.html):
//   const cm = window.mountCodeEditor(textareaEl, { filename: 'PKGBUILD' });
//   cm.getValue()            // aktueller Inhalt
//   cm.on('change', fn)      // Aenderungen beobachten
//   cm.toTextArea()          // beim Schliessen des Dialogs aufraeumen

(function () {
  // PKGBUILD ist Bash-Syntax (direkter Fit, Modus "shell"). Dockerfile hat
  // in CodeMirror 5 einen eigenen Modus. Alles andere (Patches,
  // .service-Units, Text) bleibt ohne Syntax-Highlighting.
  function modeFor(filename) {
    const name = (filename || "").toLowerCase();
    if (name === "pkgbuild") return "shell";
    if (name === "dockerfile" || name.endsWith(".dockerfile")) return "dockerfile";
    return null;
  }

  window.mountCodeEditor = function (textarea, { filename = "", onChange } = {}) {
    const mode = modeFor(filename);
    const cm = window.CodeMirror.fromTextArea(textarea, {
      mode: mode || undefined,
      lineNumbers: true,
      lineWrapping: true,
      indentUnit: 2,
      tabSize: 2,
      viewportMargin: Infinity,
    });
    if (onChange) {
      cm.on("change", function () {
        onChange(cm.getValue());
      });
    }
    return cm;
  };
})();
