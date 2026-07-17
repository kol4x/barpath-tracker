"""
Bar Path Tracker - Web App prototipo (versione con object tracking accurato)

Traccia la traiettoria del bilanciere durante esercizi come panca piana e
squat, a partire da un video registrato con lo smartphone.

Come funziona (approccio scelto per la massima accuratezza):
1. L'utente clicca direttamente sul bilanciere (o su un disco/segno ben
   visibile) nel primo fotogramma del video.
2. Un algoritmo di object tracking classico (CSRT, il piu' accurato
   disponibile in OpenCV) segue quel punto specifico fotogramma per
   fotogramma per tutta la durata del video.
3. Il percorso disegnato e' esattamente il percorso pixel-per-pixel seguito
   dal tracker: nessuna approssimazione tramite pose stimata, nessuno
   smoothing artificiale che possa deviare dal movimento reale.

Questo sostituisce l'approccio precedente basato su MediaPipe Pose (che usava
il polso come proxy del bilanciere): tracciare direttamente l'oggetto scelto
dall'utente e' molto piu' preciso, soprattutto con impugnature larghe o
inquadrature in cui il polso non coincide con il centro del bilanciere.

Stack: Streamlit + OpenCV (object tracking) + streamlit-image-coordinates
Compatibile con Python 3.14.
"""

import os
import time
import hashlib
import tempfile

import cv2
import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates
import imageio

# ----------------------------------------------------------------------------
# CONFIGURAZIONE PAGINA
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Bar Path Tracker",
    page_icon="🏋️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

CUSTOM_CSS = """
<style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 760px;
    }
    h1 {
        font-weight: 800 !important;
        letter-spacing: -0.5px;
    }
    [data-testid="stFileUploaderDropzone"] {
        border: 2px dashed #FF4B4B55;
        border-radius: 16px;
        padding: 1.2rem;
        background: linear-gradient(180deg, rgba(255,75,75,0.03), rgba(255,75,75,0.00));
    }
    .stButton > button {
        border-radius: 12px;
        font-weight: 700;
        padding: 0.7rem 1.2rem;
        transition: all 0.15s ease-in-out;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 14px rgba(0,0,0,0.15);
    }
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.7rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
        background: #16c78433;
        color: #0e8f5f;
    }
    .warn-badge {
        display: inline-block;
        padding: 0.2rem 0.7rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
        background: #ffb02e33;
        color: #b06d00;
    }
    @media (max-width: 600px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.title("🏋️ Bar Path Tracker")
st.caption(
    "Carica un video del tuo set, clicca sul bilanciere nel primo fotogramma "
    "e ottieni il video con la traiettoria reale disegnata sopra."
)

with st.expander("ℹ️ Come funziona", expanded=False):
    st.markdown(
        """
        1. **Carica** un video registrato dallo smartphone (frontale o laterale),
           con il bilanciere già visibile nel primo fotogramma.
        2. **Clicca** direttamente su un punto ben visibile e ad alto contrasto
           del bilanciere (es. il bordo di un disco, un anello del bilanciere,
           un adesivo colorato). Regola se serve la dimensione dell'area da
           seguire.
        3. Premi **Elabora Video**: un algoritmo di tracciamento (CSRT) segue
           esattamente quel punto in ogni fotogramma. La linea disegnata è il
           percorso reale seguito, senza approssimazioni.
        4. Guarda l'anteprima e **scarica** il video elaborato.

        💡 *Consigli per un tracciamento accurato*: scegli un punto ad alto
        contrasto (bordo netto, angolo, adesivo), non un'area uniforme
        (es. il centro di un disco tutto dello stesso colore); registra con
        buona luce e inquadratura fissa.
        """
    )

# ----------------------------------------------------------------------------
# UTILS
# ----------------------------------------------------------------------------


def hex_to_bgr(hex_color: str):
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


def create_tracker():
    """Crea un tracker CSRT, gestendo le diverse posizioni dell'API in OpenCV."""
    creators = []
    if hasattr(cv2, "TrackerCSRT_create"):
        creators.append(cv2.TrackerCSRT_create)
    if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
        creators.append(cv2.legacy.TrackerCSRT_create)
    last_err = None
    for creator in creators:
        try:
            return creator()
        except Exception as e:  # pragma: no cover
            last_err = e
    raise RuntimeError(
        "Impossibile creare il tracker CSRT. Verifica di avere installato "
        f"'opencv-contrib-python-headless' (errore: {last_err})."
    )


def clamp_bbox(x, y, w, h, frame_w, frame_h):
    x = max(0, min(x, frame_w - 1))
    y = max(0, min(y, frame_h - 1))
    w = max(4, min(w, frame_w - x))
    h = max(4, min(h, frame_h - y))
    return int(x), int(y), int(w), int(h)


def file_signature(uploaded_file) -> str:
    """Identificatore stabile del file caricato, per rilevare un nuovo upload."""
    return hashlib.md5(
        f"{uploaded_file.name}-{uploaded_file.size}".encode("utf-8")
    ).hexdigest()


@st.cache_data(show_spinner=False)
def extract_first_frame(video_bytes: bytes, _sig: str):
    """Estrae il primo fotogramma dal video (in RGB) e i metadati principali."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tmp.write(video_bytes)
    tmp.flush()
    tmp.close()
    cap = cv2.VideoCapture(tmp.name)
    ok, frame = cap.read()
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    os.remove(tmp.name)
    if not ok:
        return None, fps, total_frames, width, height
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return rgb_frame, fps, total_frames, width, height


# ----------------------------------------------------------------------------
# UPLOAD VIDEO
# ----------------------------------------------------------------------------
st.subheader("1️⃣ Carica il video")
uploaded_file = st.file_uploader(
    "Trascina qui il tuo video o caricalo dal rullino",
    type=["mp4", "mov", "avi", "mkv", "m4v"],
    accept_multiple_files=False,
)

if uploaded_file is None:
    st.info("👆 Carica un video per iniziare.")
    st.stop()

st.markdown('<span class="status-badge">✔ Video caricato</span>', unsafe_allow_html=True)

sig = file_signature(uploaded_file)

# Reset dello stato se viene caricato un video diverso
if st.session_state.get("video_sig") != sig:
    st.session_state["video_sig"] = sig
    st.session_state["selected_point"] = None

video_bytes = uploaded_file.getvalue()
first_frame, fps, total_frames, width, height = extract_first_frame(video_bytes, sig)

if fps <= 1 or fps > 240:
    fps = 30

if first_frame is None:
    st.error("❌ Impossibile leggere il primo fotogramma del video. Prova con un altro file (mp4 consigliato).")
    st.stop()

# ----------------------------------------------------------------------------
# 2) SELEZIONE DEL PUNTO DI PARTENZA SUL PRIMO FOTOGRAMMA
# ----------------------------------------------------------------------------
st.subheader("2️⃣ Clicca sul bilanciere nel primo fotogramma")

default_box = max(20, min(width, height) // 12)
box_size = st.slider(
    "Dimensione dell'area da seguire (px)",
    min_value=15,
    max_value=max(40, min(width, height) // 2),
    value=default_box,
    step=1,
    help="Deve coprire un dettaglio ad alto contrasto del bilanciere (bordo, "
         "adesivo, anello). Troppo piccola = facile perdere il tracciamento; "
         "troppo grande = puo' agganciare lo sfondo.",
)

display_width = min(700, width)
scale = width / display_width
display_height = int(height / scale)

preview = first_frame.copy()
selected_point = st.session_state.get("selected_point")
if selected_point is not None:
    px, py = selected_point
    half = box_size // 2
    x, y, w, h = clamp_bbox(px - half, py - half, box_size, box_size, width, height)
    cv2.rectangle(preview, (x, y), (x + w, y + h), (255, 59, 48), max(2, width // 400))
    cv2.circle(preview, (px, py), max(4, width // 250), (255, 59, 48), -1)

preview_small = cv2.resize(preview, (display_width, display_height), interpolation=cv2.INTER_AREA)

click_value = streamlit_image_coordinates(preview_small, key=f"point_selector_{sig}")

if click_value is not None:
    disp_w = click_value.get("width") or display_width
    disp_h = click_value.get("height") or display_height
    real_x = int(click_value["x"] * (width / disp_w))
    real_y = int(click_value["y"] * (height / disp_h))
    real_x = max(0, min(real_x, width - 1))
    real_y = max(0, min(real_y, height - 1))
    if st.session_state.get("selected_point") != (real_x, real_y):
        st.session_state["selected_point"] = (real_x, real_y)
        st.rerun()

if selected_point is None:
    st.warning("⚠️ Clicca su un punto del bilanciere nell'immagine qui sopra prima di procedere.")
else:
    st.caption(f"Punto selezionato: x={selected_point[0]}, y={selected_point[1]} (coordinate originali del video).")

# ----------------------------------------------------------------------------
# 3) OPZIONI GRAFICHE ESSENZIALI
# ----------------------------------------------------------------------------
st.subheader("3️⃣ Aspetto della traiettoria")
col1, col2 = st.columns(2)
with col1:
    line_color_hex = st.color_picker("Colore linea", "#FF3B30")
with col2:
    line_thickness = st.slider("Spessore linea", min_value=2, max_value=12, value=4)

LINE_COLOR_BGR = hex_to_bgr(line_color_hex)

# ----------------------------------------------------------------------------
# 4) ELABORAZIONE
# ----------------------------------------------------------------------------
st.subheader("4️⃣ Elabora")
process_clicked = st.button(
    "🚀 Elabora Video",
    use_container_width=True,
    type="primary",
    disabled=selected_point is None,
)

if process_clicked and selected_point is not None:
    input_suffix = os.path.splitext(uploaded_file.name)[1] or ".mp4"
    input_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=input_suffix)
    input_tmp.write(video_bytes)
    input_tmp.flush()
    input_path = input_tmp.name
    input_tmp.close()

    output_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name

    status_text = st.empty()
    progress_bar = st.progress(0, text="Inizializzazione...")

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        st.error("❌ Impossibile leggere il video. Prova con un altro file o formato (mp4 consigliato).")
        st.stop()

    ret, frame = cap.read()
    if not ret:
        st.error("❌ Impossibile leggere il primo fotogramma per inizializzare il tracciamento.")
        cap.release()
        st.stop()

    px, py = selected_point
    half = box_size // 2
    init_bbox = clamp_bbox(px - half, py - half, box_size, box_size, width, height)

    try:
        tracker = create_tracker()
        tracker.init(frame, init_bbox)
    except Exception as e:
        st.error(f"❌ Errore nell'inizializzazione del tracciamento: {e}")
        cap.release()
        st.stop()

    writer = imageio.get_writer(
        output_path,
        fps=fps,
        codec="libx264",
        quality=8,
        pixelformat="yuv420p",
        macro_block_size=1,
    )

    trajectory_points = []
    lost_frames = 0
    frame_idx = 0
    start_time = time.time()
    last_center = (int(px), int(py))

    while True:
        if frame_idx > 0:
            ret, frame = cap.read()
            if not ret:
                break
        frame_idx += 1

        if frame_idx == 1:
            x, y, w, h = init_bbox
            success = True
        else:
            success, bbox = tracker.update(frame)
            if success:
                x, y, w, h = bbox

        if success:
            center = (int(x + w / 2), int(y + h / 2))
            last_center = center
            trajectory_points.append(center)
        else:
            lost_frames += 1
            # Non aggiungiamo un punto fittizio: il percorso resta quello
            # reale fin dove il tracciamento e' riuscito, senza inventare
            # movimento nei fotogrammi persi.

        if len(trajectory_points) > 1:
            for i in range(1, len(trajectory_points)):
                cv2.line(
                    frame,
                    trajectory_points[i - 1],
                    trajectory_points[i],
                    LINE_COLOR_BGR,
                    line_thickness,
                    lineType=cv2.LINE_AA,
                )

        marker_color = LINE_COLOR_BGR if success else (128, 128, 128)
        cv2.circle(frame, last_center, line_thickness + 2, marker_color, -1, lineType=cv2.LINE_AA)
        cv2.circle(frame, last_center, line_thickness + 4, (255, 255, 255), 2, lineType=cv2.LINE_AA)

        frame_rgb_out = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        writer.append_data(frame_rgb_out)

        progress = min(frame_idx / max(total_frames, 1), 1.0)
        elapsed = time.time() - start_time
        progress_bar.progress(
            progress,
            text=f"Elaborazione fotogramma {frame_idx}/{total_frames or '?'} "
                 f"({progress*100:.0f}%) · {elapsed:.0f}s",
        )

    cap.release()
    writer.close()

    progress_bar.progress(1.0, text="✅ Elaborazione completata!")

    if lost_frames == 0:
        status_text.success(
            f"Video elaborato in {time.time() - start_time:.1f} secondi "
            f"({frame_idx} fotogrammi, tracciamento riuscito su tutto il video)."
        )
    else:
        loss_pct = 100 * lost_frames / max(frame_idx, 1)
        status_text.warning(
            f"Video elaborato in {time.time() - start_time:.1f} secondi. "
            f"⚠️ Il tracciamento è stato perso per {lost_frames} fotogrammi su {frame_idx} "
            f"({loss_pct:.0f}%) — probabilmente il punto scelto è uscito dall'inquadratura "
            f"o è stato oscurato. Prova a scegliere un punto più ad alto contrasto o "
            f"un'area leggermente più grande."
        )

    st.subheader("Risultato")
    st.video(output_path)

    with open(output_path, "rb") as f:
        video_out_bytes = f.read()

    st.download_button(
        label="⬇️ Scarica il video elaborato",
        data=video_out_bytes,
        file_name="bar_path_output.mp4",
        mime="video/mp4",
        use_container_width=True,
    )

    try:
        os.remove(input_path)
    except OSError:
        pass

st.markdown("---")
st.caption(
    "Prototipo · la traiettoria è calcolata tramite object tracking (CSRT) "
    "sul punto scelto dall'utente: rappresenta il movimento reale rilevato "
    "nel video, senza stime basate su punti del corpo."
)
