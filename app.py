from flask import Flask, request, render_template_string, redirect, url_for
import fitz#PyMuPDF
from PIL import Image
import pytesseract
import os, uuid
from werkzeug.utils import secure_filename


pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)


INDEX_HTML = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Leitor Acessível</title>
    <style>
      body { font-family: Arial,sans-serif; padding:20px; }
      .container { max-width:600px; margin:0 auto; background:#fff; padding:20px; border-radius:5px; }
      input, button { margin-top:10px; }
    </style>
</head>
<body>
  <div class="container">
    <h1>Leitor Acessível</h1>
    <h2>Enviar Imagem ou PDF para OCR</h2>
    <form method="POST" action="/ocr" enctype="multipart/form-data">
      <input type="file" name="file" accept="image/*,.pdf" required>
      <br>
      <button type="submit">Processar OCR</button>
    </form>
  </div>
</body>
</html>
'''


RESULT_HTML = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Accessible Document: {{ filename }}</title>

  <!-- MathJax e fontes -->
  <script>
    MathJax = {
      tex: {
        inlineMath: [['\\(', '\\)']],
        displayMath: [['$$', '$$']],
        processEscapes: true,
        processEnvironments: true
      },
      options: {
        skipHtmlTags: ['script','noscript','style','textarea','pre']
      }
    };
  </script>
  <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/antijingoist/open-dyslexic@master/open-dyslexic-regular.css">
  <link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible&family=Lexend&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/temas.css">

  <style>
    body {font-family: Verdana, Arial, sans-serif; line-height: 1.6; padding: 20px; background-color: #f0f0f0; color: #333;}

    #accessibility-controls {position: sticky; top: 0; z-index: 1000; padding: 10px; margin-bottom: 20px; border: 1px solid; border-radius: 5px;}
    body.normal-mode #accessibility-controls {background-color: #e0e0e0; border-color: #ccc; color: #000;}
    body.dark-mode #accessibility-controls {background-color: #1e1e1e; border-color: #444; color: #fff;}
    body.high-contrast-mode #accessibility-controls {background-color: #000; border-color: #00FF00; color: #00FF00;}

    #accessibility-controls button,
    #accessibility-controls select {margin: 0 5px; padding: 5px 10px; cursor: pointer;}

    .page-content {background-color: #fff; padding: 15px; margin-bottom: 20px; border: 1px solid #ddd; border-radius: 3px;}
    body.normal-mode {background-color: #f0f0f0; color: #333;}
    body.dark-mode {background-color: #121212; color: #ffffff;}
    body.high-contrast-mode {background-color: #000000;color: #00FF00;}
    body.normal-mode .page-content {background-color: #ffffff;border-color: #dddddd;}
    body.dark-mode .page-content {background-color: #1e1e1e;border-color: #444444;}
    body.high-contrast-mode .page-content {background-color: #000000;border-color: #00FF00;}

    h1, h2, h3 {border-bottom: 1px solid; padding-bottom: 0.3em;}
    body.normal-mode h1, body.normal-mode h2, body.normal-mode h3 { color: #000; border-color: #eee;}
    body.dark-mode h1, body.dark-mode h2, body.dark-mode h3 {color: #ffffff; border-color: #444;}
    body.high-contrast-mode h1, body.high-contrast-mode h2, body.high-contrast-mode h3 {color: #00FF00; border-color: #00FF00;}

    hr.page-separator {margin-top: 2em; margin-bottom: 2em; border: 1px dashed #ccc; }
    hr.footnotes-separator { margin-top: 1.5em; margin-bottom: 1em; border-style: dotted; border-width: 1px 0 0 0; }

    .footnotes-section { margin-top: 1em; padding-top: 0.5em; }
    .footnotes-list { list-style-type: decimal; padding-left: 20px; font-size: 0.9em; }
    .footnotes-list li { margin-bottom: 0.5em; }
    .footnotes-list li a { text-decoration: none; }

    .sr-only {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border-width: 0;
    }

    p i, span i {color: #555; font-style: italic;}

    sup > a {
        text-decoration: none;
        color: #0066cc;
    }
    sup > a:hover {
        text-decoration: underline;
    }
  </style>
</head>

<body class="normal-mode">
  <!-- CONTROLES DE ACESSIBILIDADE -->
  <div id="accessibility-controls">
    <span>Tamanho da Fonte:</span>
    <button id="decreaseFont">A-</button>
    <button id="increaseFont">A+</button>

    <label for="fontSelector">Fonte:</label>
    <select id="fontSelector">
      <option>Atkinson Hyperlegible</option>
      <option>Lexend</option>
      <option>OpenDyslexicRegular</option>
      <option>Verdana</option>
      <option>Arial</option>
      <option>Times New Roman</option>
      <option>Courier New</option>
    </select>

    <span>Leitura:</span>
    <button id="play">▶️</button>
    <button id="pause">⏸️</button>
    <button id="stop">⏹️</button>

    <label for="themeSelector">Tema:</label>
    <select id="themeSelector">
      <option value="normal">Normal</option>
      <option value="dark">Modo Escuro</option>
      <option value="high-contrast">Alto Contraste</option>
    </select>
  </div>

  <!-- SEU CONTEÚDO -->
  <div class="page-content">
    <h1>Resultado do OCR</h1>
    <h2>{{ filename }}</h2>
    <p>{{ text }}</p>
    <a href="/">← Voltar</a>
  </div>

  <!-- TODOS OS SCRIPTS APÓS O DOM TER SIDO CARREGADO -->
  <script>
    // variáveis de controle
    let currentFontSize = 16;
    const fonts = ['Atkinson Hyperlegible','Lexend','OpenDyslexicRegular','Verdana','Arial','Times New Roman','Courier New'];
    let currentFontIndex = 0;
    const synth = window.speechSynthesis;
    let utterance, isPaused = false;

    // funções
    function applyFontSize() {
      document.querySelectorAll('.page-content').forEach(el => {
        el.style.fontSize = currentFontSize + 'px';
      });
    }

    function applyFontFamily() {
      const ff = fonts[currentFontIndex];
      document.querySelectorAll('.page-content').forEach(el => {
        el.style.fontFamily = ff + ', sans-serif';
      });
    }

    function changeTheme(mode) {
      document.body.classList.remove('normal-mode','dark-mode','high-contrast-mode');
      document.body.classList.add(mode + '-mode');
    }

    function getTextToSpeak() {
      const sel = window.getSelection().toString();
      if (sel) return sel;
      return document.querySelector('.page-content').innerText;
    }

    function speak() {
      const text = getTextToSpeak();
      if (!text) return alert('Nada para ler');
      if (synth.speaking) return;
      utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'pt-BR';
      synth.speak(utterance);
    }

    function pauseSpeech() { if (synth.speaking) { synth.pause(); isPaused = true; } }
    function resumeSpeech() { if (isPaused) { synth.resume(); isPaused = false; } }
    function stopSpeech() { synth.cancel(); isPaused = false; }

    // eventos
    document.getElementById('decreaseFont').onclick = () => { currentFontSize = Math.max(10, currentFontSize - 2); applyFontSize(); };
    document.getElementById('increaseFont').onclick = () => { currentFontSize = Math.min(40, currentFontSize + 2); applyFontSize(); };
    document.getElementById('fontSelector').onchange = e => { currentFontIndex = fonts.indexOf(e.target.value); applyFontFamily(); };

    document.getElementById('play').onclick = () => { if (isPaused) resumeSpeech(); else speak(); };
    document.getElementById('pause').onclick = pauseSpeech;
    document.getElementById('stop').onclick = stopSpeech;

    document.getElementById('themeSelector').onchange = e => { changeTheme(e.target.value); };

    // inicialização
    document.addEventListener('DOMContentLoaded', () => {
      applyFontSize();
      applyFontFamily();
      changeTheme('normal');
      document.getElementById('fontSelector').value = fonts[0];
      document.getElementById('themeSelector').value = 'normal';
    });
  </script>
</body>
</html>

'''


@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/ocr', methods=['POST'])
def ocr():
    uploaded = request.files.get('file')
    if not uploaded:
        return redirect(url_for('index'))

    # Nome seguro e pasta temporária
    original_name = secure_filename(uploaded.filename)
    tmp_dir = 'tmp'
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_name = f"tmp_{uuid.uuid4().hex}_{original_name}"
    tmp_path = os.path.join(tmp_dir, tmp_name)

    # Salva o arquivo temporário
    uploaded.save(tmp_path)

    texts = []
    ext = os.path.splitext(original_name)[1].lower()

    try:
        if ext == '.pdf':
            # PDF: processa todas as páginas
            doc = fitz.open(tmp_path)
            for page in doc:
                pix = page.get_pixmap(dpi=200, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                txt = pytesseract.image_to_string(img, lang='por+eng')
                texts.append(txt)
            doc.close()
        else:
            # Imagem única
            with Image.open(tmp_path) as img:
                txt = pytesseract.image_to_string(img, lang='por+eng')
                texts.append(txt)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    full_text = "\n\n".join(texts)
    return render_template_string(RESULT_HTML, filename=original_name, text=full_text)

if __name__ == '__main__':
    app.run(debug=True)
