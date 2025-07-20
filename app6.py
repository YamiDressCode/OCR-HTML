from flask import Flask, request, render_template_string, redirect, url_for, send_file
import fitz
from PIL import Image
import pytesseract
import os, uuid # 'os' é importante aqui
from werkzeug.utils import secure_filename
import google.generativeai as genai
import json
import speech_recognition as sr
import pyttsx3
import io
from pydub import AudioSegment
import tempfile # Ainda usaremos tempfile, mas direcionaremos sua base

# --- Configurações Iniciais ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)

genai.configure(api_key="")

model = genai.GenerativeModel('models/gemini-2.0-flash')

engine = pyttsx3.init()
voices = engine.getProperty('voices')
for voice in voices:
    if "brazil" in voice.name.lower() or "portuguese" in voice.name.lower():
        engine.setProperty('voice', voice.id)
        break
else:
    engine.setProperty('voice', voices[0].id)
engine.setProperty('rate', 150)
engine.setProperty('volume', 1.0)
# --- Fim das Configurações Iniciais ---

# --- Definição da Pasta Temporária Customizada ---
# Pega o diretório do script atual e anexa 'temp_audios'
# Isso garante que a pasta temporária seja relativa ao seu projeto
CUSTOM_TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_audios')

# Garante que o diretório exista. Se não existir, ele será criado.
os.makedirs(CUSTOM_TEMP_DIR, exist_ok=True)

# Opcional: Define a variável de ambiente TEMP para a sua pasta customizada
# Isso faz com que 'tempfile' use essa pasta por padrão para tudo,
# mas podemos ser mais específicos na rota.
# os.environ['TMPDIR'] = CUSTOM_TEMP_DIR # Para sistemas Unix-like
# os.environ['TEMP'] = CUSTOM_TEMP_DIR   # Para Windows
# os.environ['TMP'] = CUSTOM_TEMP_DIR    # Para Windows
# ^^^ Comentadas, pois vamos passar 'dir' diretamente para NamedTemporaryFile

INDEX_HTML = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Leitor Acessível</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5; }
        .container { max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
<div class="container">
    <h1>🧠 Leitor Acessível</h1>
    <form method="POST" action="/ocr" enctype="multipart/form-data">
        <label>Escolha um arquivo PDF ou imagem:</label><br>
        <input type="file" name="file" accept="image/*,.pdf" required><br><br>
        <button type="submit">📄 Processar OCR</button>
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
  <title>{{ filename }}</title>
  <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/antijingoist/open-dyslexic@master/open-dyslexic-regular.css">
  <link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible&family=Lexend&display=swap" rel="stylesheet">
  <style>
    body { font-family: Verdana, Arial, sans-serif; line-height: 1.6; padding: 20px; background-color: #f0f0f0; color: #333; }

    #accessibility-controls {
      position: sticky; top: 0; z-index: 1000;
      padding: 10px; margin-bottom: 20px;
      border: 1px solid; border-radius: 5px;
    }

    body.normal-mode #accessibility-controls {
      background-color: #e0e0e0; border-color: #ccc; color: #000;
    }

    body.dark-mode #accessibility-controls {
      background-color: #1e1e1e; border-color: #444; color: #fff;
    }

    body.high-contrast-mode #accessibility-controls {
      background-color: #000; border-color: #00FF00; color: #00FF00;
    }

    #accessibility-controls button,
    #accessibility-controls select {
      margin: 0 5px; padding: 5px 10px; cursor: pointer;
    }

    .page-content {
      background-color: #fff; padding: 15px;
      margin-bottom: 20px; border: 1px solid #ddd;
      border-radius: 3px;
    }

    body.normal-mode { background-color: #f0f0f0; color: #333; }
    body.dark-mode { background-color: #121212; color: #ffffff; }
    body.high-contrast-mode { background-color: #000000; color: #00FF00; }

    body.normal-mode .page-content { background-color: #ffffff; border-color: #dddddd; }
    body.dark-mode .page-content { background-color: #1e1e1e; border-color: #444444; }
    body.high-contrast-mode .page-content { background-color: #000000; border-color: #00FF00; }

    h1, h2, h3 {
      border-bottom: 1px solid; padding-bottom: 0.3em;
    }

    body.normal-mode h1, body.normal-mode h2, body.normal-mode h3 {
      color: #000; border-color: #eee;
    }

    body.dark-mode h1, body.dark-mode h2, body.dark-mode h3 {
      color: #fff; border-color: #444;
    }

    body.high-contrast-mode h1, body.high-contrast-mode h2, body.high-contrast-mode h3 {
      color: #00FF00; border-color: #00FF00;
    }

    hr.page-separator {
      margin-top: 2em; margin-bottom: 2em;
      border: 1px dashed #ccc;
    }

    hr.footnotes-separator {
      margin-top: 1.5em; margin-bottom: 1em;
      border-style: dotted; border-width: 1px 0 0 0;
    }

    .footnotes-section { margin-top: 1em; padding-top: 0.5em; }
    .footnotes-list { list-style-type: decimal; padding-left: 20px; font-size: 0.9em; }
    .footnotes-list li { margin-bottom: 0.5em; }
    .footnotes-list li a { text-decoration: none; }

    .sr-only {
      position: absolute; width: 1px; height: 1px;
      padding: 0; margin: -1px; overflow: hidden;
      clip: rect(0, 0, 0, 0); white-space: nowrap; border-width: 0;
    }

    p i, span i { color: #555; font-style: italic; }

    sup > a { text-decoration: none; color: #0066cc; }
    sup > a:hover { text-decoration: underline; }
  </style>
</head>

<body class="normal-mode">
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

    <button onclick="copyText()">📋 Copiar</button>
    <button onclick="saveHTML()">💾 Salvar</button>

    <button id="talkToAI">🗣️ Falar com IA</button>
    <span id="recordingStatus" style="margin-left: 10px; color: red;"></span>
  </div>

    <div class="page-content">
    <h1>Resultado OCR – {{ filename }}</h1>
    <div>{{ text|safe }}</div>

    <form method="POST" action="/gerar_html">
      <input type="hidden" name="ocr_texto" value="{{ text|e }}">
      <button type="submit">🧠 Reestruturar com IA (Gemini)</button>
    </form>

    <div class="actions">
      <a href="/">← Voltar</a>
    </div>
  </div>

    <script>
    let currentFontSize = 16;
    const fonts = ['Atkinson Hyperlegible','Lexend','OpenDyslexicRegular','Verdana','Arial','Times New Roman','Courier New'];
    let currentFontIndex = 0;
    const synth = window.speechSynthesis;
    let utterance, isPaused = false;
    let mediaRecorder;
    let audioChunks = [];
    const talkToAIButton = document.getElementById('talkToAI');
    const recordingStatus = document.getElementById('recordingStatus');

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
      return sel || document.querySelector('.page-content').innerText;
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

    document.getElementById('decreaseFont').onclick = () => {
      currentFontSize = Math.max(10, currentFontSize - 2);
      applyFontSize();
    };
    document.getElementById('increaseFont').onclick = () => {
      currentFontSize = Math.min(40, currentFontSize + 2);
      applyFontSize();
    };
    document.getElementById('fontSelector').onchange = e => {
      currentFontIndex = fonts.indexOf(e.target.value);
      applyFontFamily();
    };

    document.getElementById('play').onclick = () => {
      if (isPaused) resumeSpeech();
      else speak();
    };
    document.getElementById('pause').onclick = pauseSpeech;
    document.getElementById('stop').onclick = stopSpeech;

    document.getElementById('themeSelector').onchange = e => {
      changeTheme(e.target.value);
    };

    function copyText() {
      const text = document.querySelector('.page-content').innerText;
      navigator.clipboard.writeText(text).then(() => alert('Texto copiado!'));
    }

    function saveHTML() {
      const content = document.documentElement.outerHTML;
      const blob = new Blob([content], { type: 'text/html' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'documento_acessivel.html';
      link.click();
    }

    // LÓGICA PARA INTERAÇÃO COM A IA POR VOZ - AJUSTADA PARA GARANTIR COMPATIBILIDADE
    talkToAIButton.onclick = async () => {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            talkToAIButton.textContent = '🗣️ Falar com IA';
            recordingStatus.textContent = '';
        } else {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                
                // Definir o mimeType para WebM com Opus, que é um formato eficiente e amplamente suportado
                // pelo MediaRecorder e que o pydub consegue lidar bem.
                const options = { mimeType: 'audio/webm;codecs=opus' };
                mediaRecorder = new MediaRecorder(stream, options);
                
                audioChunks = [];

                mediaRecorder.ondataavailable = event => {
                    audioChunks.push(event.data);
                };

                mediaRecorder.onstop = async () => {
                    const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType }); // Usa o tipo MIME real da gravação
                    const formData = new FormData();
                    formData.append('audio', audioBlob, 'query.webm'); // Envia como .webm

                    recordingStatus.textContent = 'Enviando e processando...';

                    try {
                        const response = await fetch('/ask_ai_voice', {
                            method: 'POST',
                            body: formData
                        });

                        if (response.ok) {
                            const audioResponseBlob = await response.blob();
                            const audioUrl = URL.createObjectURL(audioResponseBlob);
                            const audio = new Audio(audioUrl);
                            audio.onended = () => {
                                recordingStatus.textContent = 'Pronto!';
                            };
                            audio.play();
                        } else {
                            const errorText = await response.text();
                            recordingStatus.textContent = `Erro: ${errorText}`;
                            alert('Erro ao se comunicar com a IA: ' + errorText);
                        }
                    } catch (error) {
                        recordingStatus.textContent = `Erro de rede: ${error.message}`;
                        console.error('Erro ao enviar áudio para a IA:', error);
                        alert('Erro de conexão ao enviar áudio.');
                    } finally {
                        stream.getTracks().forEach(track => track.stop()); // Para o microfone
                    }
                };

                mediaRecorder.start();
                talkToAIButton.textContent = '🔴 Parar Gravação';
                recordingStatus.textContent = 'Gravando...';
            } catch (error) {
                console.error('Erro ao acessar o microfone:', error);
                alert('Não foi possível acessar o microfone. Verifique as permissões.');
            }
        }
    };


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


def gerar_html_acessivel_com_gemini(texto_ocr):
    prompt = f"""
    Você é uma IA que transforma textos escaneados via OCR em documentos HTML acessíveis.
    Suas tarefas incluem:
    - Corrigir erros de OCR
    - Detectar e formatar títulos, listas, tabelas e seções
    - Converter equações para LaTeX (exibidas com MathJax)
    - Estruturar o conteúdo com marcação HTML limpa
    - Tornar o conteúdo ideal para leitores de tela
    Você atuará como um conversor de expressões matemáticas para uma versão descritiva, em linguagem natural, ideal para leitores de tela e acessibilidade web.
    O conteúdo a seguir é extraído por OCR a partir de documentos didáticos contendo expressões matemáticas (como derivadas, limites, integrais, funções, matrizes, planilhas etc).
    Sua tarefa é:
    1. Corrigir qualquer erro ortográfico ou de OCR;
    2. Converter expressões matemáticas para texto descritivo, seguindo os exemplos abaixo;
    3. Manter o conteúdo formatado com marcação HTML simples e/ou MathJax (`\( ... \)` para inline e `$$ ... $$` para blocos);
    4. Retornar o resultado em **HTML completo**, pronto para ser exibido em navegadores com suporte a leitores automáticos.
    ### Exemplo de Conversões:
    `f(x) = x^2 + 1` → `A função f de x é igual a x ao quadrado mais um. Escrito como \( f(x) = x^2 + 1 \)`
    `lim x→0 f(x)` → `O limite de f de x quando x tende a zero. Escrito como 
    `∫x^2 dx` → `A integral de x ao quadrado em relação a x. Escrito como
    `2,34` → `dois vírgula três quatro`
    `Matriz [[1, 2], [3, 4]]` → `Matriz de duas linhas e duas colunas com os elementos: primeira linha um e dois, segunda linha três e quatro`
    `f'(x)` → `Derivada da função f em relação a x. Escrito como \( f'(x) \)`
    `|x|` → `Valor absoluto de x. Escrito como \( |x| \)`
    `Δx` → `Variação de x. Escrito como \( \Delta x \)`
    ### Importante:
    - Sempre que possível, forneça as duas formas: descritiva e matemática.
- Mantenha títulos, subtítulos e parágrafos intactos, substituindo apenas os trechos matemáticos ou ambíguos.
- Conserve os separadores visuais e use HTML para listas, ênfases e headings.
- Retorne o resultado em HTML **completo** entre `<html>...</html>`.

    Gere o corpo HTML (sem <html> ou <head>), apenas o conteúdo principal com marcação semântica:


    Texto OCR:
    \"\"\"{texto_ocr}\"\"\"
    """

    response = model.generate_content(prompt)
    return response.text

# Nova função para interagir com a IA por voz
def ask_gemini_and_get_audio(text_input):
    prompt = f"O usuário perguntou: '{text_input}'. Responda de forma concisa e útil."
    ai_response = model.generate_content(prompt).text

    audio_buffer = io.BytesIO()
    try:
        # Usa a pasta temporária customizada para o pyttsx3 também
        with tempfile.NamedTemporaryFile(delete=True, suffix=".wav", dir=CUSTOM_TEMP_DIR) as fp:
            engine.save_to_file(ai_response, fp.name)
            engine.runAndWait()
            fp.seek(0)
            audio_buffer.write(fp.read())
        audio_buffer.seek(0)
    except Exception as e:
        print(f"Erro ao gerar áudio com pyttsx3: {e}")
        error_message = "Desculpe, tive um problema ao gerar a resposta de áudio."
        try:
            with tempfile.NamedTemporaryFile(delete=True, suffix=".wav", dir=CUSTOM_TEMP_DIR) as fp:
                engine.save_to_file(error_message, fp.name)
                engine.runAndWait()
                fp.seek(0)
                audio_buffer.write(fp.read())
            audio_buffer.seek(0)
        except Exception as inner_e:
            print(f"Erro ao gerar mensagem de erro de áudio de fallback: {inner_e}")
            audio_buffer = io.BytesIO()
        ai_response = error_message

    return audio_buffer, ai_response

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/ocr', methods=['POST'])
def ocr():
    uploaded = request.files.get('file')
    if not uploaded:
        return redirect(url_for('index'))

    original_name = secure_filename(uploaded.filename)
    tmp_dir = 'tmp' # Esta é para OCR, pode manter separada ou integrar na nova, mas é diferente da de áudio
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_name = f"tmp_{uuid.uuid4().hex}_{original_name}"
    tmp_path = os.path.join(tmp_dir, tmp_name)
    uploaded.save(tmp_path)

    texts = []
    ext = os.path.splitext(original_name)[1].lower()

    try:
        if ext == '.pdf':
            doc = fitz.open(tmp_path)
            for page in doc:
                pix = page.get_pixmap(dpi=200, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                txt = pytesseract.image_to_string(img, lang='por+eng')
                texts.append(txt)
            doc.close()
        else:
            with Image.open(tmp_path) as img:
                txt = pytesseract.image_to_string(img, lang='por+eng')
                texts.append(txt)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    full_text = "\n\n".join(texts)
    return render_template_string(RESULT_HTML, filename=original_name, text=full_text)

@app.route('/gerar_html', methods=['POST'])
def gerar_html():
    texto_ocr = request.form.get('ocr_texto', '')
    if not texto_ocr.strip():
        return "Texto vazio.", 400

    html_resultado = gerar_html_acessivel_com_gemini(texto_ocr)
    
    return render_template_string(RESULT_HTML, filename="Documento Adaptado", text=html_resultado)

@app.route('/ask_ai_voice', methods=['POST'])
def ask_ai_voice():
    if 'audio' not in request.files:
        return "Nenhum arquivo de áudio recebido.", 400

    audio_file = request.files['audio']
    audio_data = audio_file.read()

    r = sr.Recognizer()
    try:
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_data))
        
        # Usa a pasta temporária customizada especificada no início do script
        # O parâmetro 'dir' direciona tempfile para usar essa pasta
        with tempfile.NamedTemporaryFile(delete=True, suffix=".wav", dir=CUSTOM_TEMP_DIR) as temp_wav_file:
            audio_segment.export(temp_wav_file.name, format="wav", codec="pcm_s16le")
            temp_wav_file.seek(0)
            
            with sr.AudioFile(temp_wav_file.name) as source:
                audio_listened = r.record(source)

            user_question = r.recognize_google(audio_listened, language='pt-BR')
            print(f"Pergunta do usuário: {user_question}")

            audio_response_buffer, ai_text_response = ask_gemini_and_get_audio(user_question)
            print(f"Resposta da IA: {ai_text_response}")

            return send_file(audio_response_buffer, mimetype='audio/wav', as_attachment=False)

    except sr.UnknownValueError:
        print("Não foi possível entender o áudio.")
        return "Não foi possível entender sua fala. Poderia repetir?", 400
    except sr.RequestError as e:
        print(f"Erro no serviço de reconhecimento de fala; verifique sua conexão com a internet: {e}")
        return f"Erro no serviço de reconhecimento de fala: {e}", 500
    except Exception as e:
        print(f"Ocorreu um erro geral na rota /ask_ai_voice: {e}")
        return f"Ocorreu um erro inesperado: {e}", 500

if __name__ == '__main__':
    app.run(debug=True)
