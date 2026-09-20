"""
PlyC (Ply Chess) - Açılış Ağacı Süper-Hesaplama Motoru
=====================================================
Bir açılış pozisyonundan başlayarak, her düğümde:
  - MultiPV ile en iyi N hamleyi bulur, "mükemmel/harika/iyi" olarak etiketler
  - Tek büyük multipv taramasıyla "tuzak" (sub-optimal ama öğretici) hamle adaylarını bulur,
    bunları da tam analiz ederek ağaca ekler
  - max_ply derinliğine kadar, ply-decay ile daralarak recursive devam eder

Çıktı: tree.json (ham veri) + variations.pgn (Lichess Study'ye import edilebilir)
"""
import json
import time
import argparse
import os
import urllib.request
import chess
import chess.engine
import chess.pgn
import sys

# ---------------------------------------------------------------------------
# Çoklu dil desteği (i18n)
# ---------------------------------------------------------------------------
LABEL_DISPLAY = {
    "tr": {"excellent": "MÜKEMMEL", "great": "HARİKA", "good": "İYİ", "trap": "TUZAK"},
    "en": {"excellent": "EXCELLENT", "great": "GREAT", "good": "GOOD", "trap": "TRAP"},
}

STRINGS = {
    "tr": {
        "start": "Başlangıç",
        "config_line": "Config: multipv={multipv}, max_ply={max_ply}, time_per_node={time}s",
        "side_line": "Taraf: {side}",
        "total_time": "Toplam süre",
        "outputs_written": "Çıktılar yazıldı",
        "downloading": "İndiriliyor: {url}",
        "engine_saved": "Motor kaydedildi: {path}",
        "engine_saved_hint": "Kullanmak için config'te \"engine_path\" alanını bu yola ayarla (veya --motor {path} kullan).",
        "preset_not_found": "Seviye ön-ayarı bulunamadı: {seviye} (aranan dosya: {filename})",
        "margin": "fark",
    },
    "en": {
        "start": "Starting position",
        "config_line": "Config: multipv={multipv}, max_ply={max_ply}, time_per_node={time}s",
        "side_line": "Side: {side}",
        "total_time": "Total time",
        "outputs_written": "Outputs written",
        "downloading": "Downloading: {url}",
        "engine_saved": "Engine saved: {path}",
        "engine_saved_hint": "To use it, set \"engine_path\" in your config to this path (or use --motor {path}).",
        "preset_not_found": "Level preset not found: {seviye} (looking for file: {filename})",
        "margin": "gap",
    },
}

SIDE_DISPLAY = {
    "tr": {"beyaz": "Beyaz", "siyah": "Siyah"},
    "en": {"beyaz": "White", "siyah": "Black"},
}


def get_language(cli_lang=None):
    """Dil öncelik sırası: CLI parametresi > ortam değişkeni > sistem geneli
    ayar dosyası (kurulum sırasında debconf tarafından yazılır) > varsayılan 'tr'."""
    if cli_lang:
        return cli_lang
    env_lang = os.environ.get("PLYC_LANG")
    if env_lang in STRINGS:
        return env_lang
    for path in ("/etc/plyc/language.conf", os.path.expanduser("~/.config/plyc/language.conf")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                val = f.read().strip()
            if val in STRINGS:
                return val
        except (FileNotFoundError, OSError):
            pass
    return "tr"


def t(lang, key, **kwargs):
    s = STRINGS.get(lang, STRINGS["tr"]).get(key, key)
    return s.format(**kwargs) if kwargs else s


def label_display(lang, label):
    return LABEL_DISPLAY.get(lang, LABEL_DISPLAY["tr"]).get(label, label)


def add_engine(url, name, lang):
    """Verilen URL'den bir motor indirir. Ham binary VEYA .tar/.tar.gz/.zip arşivi
    olabilir; arşivse içinden çalıştırılabilir dosyayı bulup çıkarır. Yerel yolu döner."""
    import tarfile
    import zipfile
    import tempfile
    import stat

    engines_dir = os.path.expanduser("~/.local/share/plyc/engines")
    os.makedirs(engines_dir, exist_ok=True)

    print(t(lang, "downloading", url=url))
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_name = os.path.basename(url.split("?")[0]) or "download"
        tmp_path = os.path.join(tmpdir, raw_name)
        urllib.request.urlretrieve(url, tmp_path)

        final_name = name or os.path.splitext(raw_name)[0].replace(".tar", "")
        dest = os.path.join(engines_dir, final_name)

        extracted_bin = None
        if tarfile.is_tarfile(tmp_path):
            extract_dir = os.path.join(tmpdir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with tarfile.open(tmp_path) as tf:
                tf.extractall(extract_dir)
            extracted_bin = _find_engine_binary(extract_dir)
        elif zipfile.is_zipfile(tmp_path):
            extract_dir = os.path.join(tmpdir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(tmp_path) as zf:
                zf.extractall(extract_dir)
            extracted_bin = _find_engine_binary(extract_dir)

        if extracted_bin:
            with open(extracted_bin, "rb") as src, open(dest, "wb") as dst:
                dst.write(src.read())
        else:
            # arşiv değil, doğrudan ham binary
            with open(tmp_path, "rb") as src, open(dest, "wb") as dst:
                dst.write(src.read())

    st = os.stat(dest)
    os.chmod(dest, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(t(lang, "engine_saved", path=dest))
    print(t(lang, "engine_saved_hint", path=dest))
    return dest


def _find_engine_binary(extract_dir):
    """Çıkarılmış arşiv içinde en olası motor binary'sini bulur:
    'stockfish' geçen, uzantısız (.txt/.md/.nnue değil) en büyük dosya."""
    best = None
    best_size = -1
    for root, _, files in os.walk(extract_dir):
        for fname in files:
            lower = fname.lower()
            if any(lower.endswith(ext) for ext in (".txt", ".md", ".nnue", ".gz", ".zip")):
                continue
            full = os.path.join(root, fname)
            size = os.path.getsize(full)
            looks_like_engine = "stockfish" in lower or os.access(full, os.X_OK)
            if looks_like_engine and size > best_size:
                best = full
                best_size = size
    return best


PRESET_FILES = {"hizli": "config_hizli_test.json", "orta": "config_orta.json", "derin": "config.json"}
PRESET_SEARCH_DIRS = [
    os.path.dirname(os.path.abspath(sys.argv[0])) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__)),
    "/usr/share/plyc",
    os.path.expanduser("~/.config/plyc"),
    ".",
]


def resolve_config_path(args, lang):
    if args.config:
        return args.config
    seviye = args.seviye or "derin"
    filename = PRESET_FILES[seviye]
    for d in PRESET_SEARCH_DIRS:
        candidate = os.path.join(d, filename)
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(t(lang, "preset_not_found", seviye=seviye, filename=filename))

def load_config(path="config_test.json"):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v["value"] for k, v in raw.items() if not k.startswith("_")}


def label_for_margin(margin_cp, cfg):
    """margin_cp: en iyi hamleden ne kadar kötü (pozitif sayı, cp cinsinden).
    Dönen değerler dilden bağımsız iç kodlardır: excellent/great/good/trap/None."""
    if margin_cp <= cfg["excellent_cp_margin"]:
        return "excellent"
    if margin_cp <= cfg["great_cp_margin"]:
        return "great"
    if margin_cp <= cfg["good_cp_margin"]:
        return "good"
    if cfg["trap_cp_min"] <= margin_cp <= cfg["trap_cp_max"]:
        return "trap"
    return None  # ne iyi ne öğretici tuzak -> atla


def score_to_cp(score, board):
    """python-chess PovScore -> side-to-move'a göre centipawn int (mat ise büyük sayı)."""
    pov = score.pov(board.turn)
    if pov.is_mate():
        mate_in = pov.mate()
        return 100000 - abs(mate_in) if mate_in > 0 else -100000 + abs(mate_in)
    return pov.score()


def analyze_node(engine, board, cfg, log_prefix="", multipv_n=None, trap_n=None, lang="tr"):
    """Bir pozisyonda: multipv iyi hamleler + tuzak adayları -> etiketli hamle listesi döner.
    multipv_n / trap_n verilirse cfg'deki tabanları geçersiz kılar (ply-decay için)."""
    moves_out = []
    eff_multipv = multipv_n if multipv_n is not None else cfg["multipv"]
    eff_trap_n = trap_n if trap_n is not None else cfg["trap_candidates_root"]

    # 1) Ana MultiPV analizi (iyi hamleler)
    limit = chess.engine.Limit(time=cfg["time_per_node_seconds"])
    info_list = engine.analyse(
        board, limit, multipv=max(1, eff_multipv)
    )
    if isinstance(info_list, dict):
        info_list = [info_list]

    # Önce tüm hamle/eval çiftlerini topla (iki geçişli: MultiPV kısa aramada
    # sıralama gürültülü olabilir, gerçek en iyiyi ancak hepsini görünce biliriz).
    raw = []
    seen_moves = set()
    for info in info_list:
        if "pv" not in info or not info["pv"]:
            continue
        mv = info["pv"][0]
        cp = score_to_cp(info["score"], board)
        raw.append((mv, cp, info["pv"]))
        seen_moves.add(mv.uci())

    best_cp = max(cp for _, cp, _ in raw) if raw else 0

    for mv, cp, pv in raw:
        margin = max(0, best_cp - cp)
        label = label_for_margin(margin, cfg)
        if label:
            moves_out.append({
                "move_uci": mv.uci(),
                "move_san": board.san(mv),
                "cp": cp,
                "margin_from_best": margin,
                "label": label,
                "pv": [m.uci() for m in pv[:6]],
            })
        print(f"{log_prefix}  [{label_display(lang, label) if label else '-'}] {board.san(mv)}  cp={cp} ({t(lang, 'margin')}={margin})")

    # 2) Tuzak adayları: 26 ayrı push/pop/analyse yerine TEK büyük multipv
    #    çağrısıyla tüm legal hamleleri sığ derinlikte ucuza sırala.
    #    eff_trap_n == 0 ise (derin ply'larda) bu pahalı taramayı TAMAMEN atla.
    legal_moves = list(board.legal_moves)
    remaining = [mv for mv in legal_moves if mv.uci() not in seen_moves]
    candidates = []
    if remaining and eff_trap_n > 0:
        n_scan = len(legal_moves)  # tüm hamleleri iste (bazıları zaten seen_moves'ta)
        trap_limit = chess.engine.Limit(depth=cfg["trap_scan_depth"])
        scan_info = engine.analyse(board, trap_limit, multipv=n_scan)
        if isinstance(scan_info, dict):
            scan_info = [scan_info]
        for info in scan_info:
            if "pv" not in info or not info["pv"]:
                continue
            mv = info["pv"][0]
            if mv.uci() in seen_moves:
                continue
            cp = score_to_cp(info["score"], board)  # push yok, board.turn zaten doğru taraf
            margin = max(0, best_cp - cp)
            if cfg["trap_cp_min"] <= margin <= cfg["trap_cp_max"]:
                candidates.append((mv, cp, margin))

    # En makul (en az kötü) birkaç tuzak adayını tam sürede tekrar analiz et
    candidates.sort(key=lambda x: x[2])  # en küçük margin önce
    for mv, approx_cp, approx_margin in candidates[:eff_trap_n]:
        board.push(mv)
        try:
            info = engine.analyse(board, chess.engine.Limit(time=cfg["time_per_node_seconds"]))
            cp = -score_to_cp(info["score"], board)
            pv_rest = [m.uci() for m in info.get("pv", [])[:5]]
        finally:
            board.pop()
        margin = max(0, best_cp - cp)
        label = label_for_margin(margin, cfg)
        if label == "trap":
            moves_out.append({
                "move_uci": mv.uci(),
                "move_san": board.san(mv),
                "cp": cp,
                "margin_from_best": margin,
                "label": label,
                "pv": [mv.uci()] + pv_rest,
            })
            print(f"{log_prefix}  [{label_display(lang, 'trap')}] {board.san(mv)}  cp={cp} ({t(lang, 'margin')}={margin})")

    return moves_out


def decayed_counts(cfg, ply_index):
    """ply_index: kökte 0, her ply'da +1. Her ply'da 1 azalt, tabanda (floor) sabitlen.
    Bu, agacin derinlerde 'sadece ana devam' moduna hizlica gecmesini saglar."""
    root_multipv = cfg["multipv"]
    floor_multipv = cfg["multipv_floor"]
    multipv_n = max(floor_multipv, root_multipv - ply_index)

    root_trap = cfg["trap_candidates_root"]
    floor_trap = cfg["trap_candidates_floor"]
    trap_n = max(floor_trap, root_trap - ply_index)

    return multipv_n, trap_n


def build_tree(engine, board, cfg, ply_left, ply_index=0, lang="tr"):
    node = {"fen": board.fen(), "moves": []}
    if ply_left <= 0 or board.is_game_over():
        return node

    multipv_n, trap_n = decayed_counts(cfg, ply_index)
    moves = analyze_node(
        engine, board, cfg,
        log_prefix="  " * ply_index,
        multipv_n=multipv_n, trap_n=trap_n, lang=lang,
    )
    for mdata in moves:
        mv = chess.Move.from_uci(mdata["move_uci"])
        if mdata["cp"] < cfg["min_eval_to_continue_cp"]:
            mdata["children"] = None  # dal kesildi, zaten kötü
            node["moves"].append(mdata)
            continue
        board.push(mv)
        child = build_tree(engine, board, cfg, ply_left - 1, ply_index + 1, lang=lang)
        board.pop()
        mdata["children"] = child
        node["moves"].append(mdata)
    return node


def tree_to_pgn(tree, board, game_node, cfg, root_moves_san, lang="tr"):
    """tree.json yapısını python-chess Game/variation ağacına çevirir."""
    for mdata in tree.get("moves", []):
        label = mdata["label"]
        mv = chess.Move.from_uci(mdata["move_uci"])
        child_node = game_node.add_variation(mv)
        comment_bits = [label_display(lang, label), f"eval={mdata['cp']/100:.2f}"]
        child_node.comment = " | ".join(comment_bits)
        if mdata.get("children") and mdata["children"].get("moves"):
            board.push(mv)
            tree_to_pgn(mdata["children"], board, child_node, cfg, root_moves_san, lang=lang)
            board.pop()


def parse_args():
    p = argparse.ArgumentParser(
        prog="plyc",
        description="PlyC (Ply Chess) - açılış ağacı süper-hesaplama motoru"
    )
    p.add_argument("--config", default=None,
                    help="Config dosyasının tam yolu. Verilmezse --seviye kullanılır.")
    p.add_argument("--seviye", choices=["hizli", "orta", "derin"], default=None,
                    help="Hazır ayar seviyesi: hizli (test), orta, derin (üretim). "
                         "--config verilmezse varsayılan 'derin'.")
    p.add_argument("--opening", default="d4 d5 c4",
                    help="Başlangıç hamleleri, SAN, boşlukla ayrılmış. Örn: 'e4 e5 Nf3'")
    p.add_argument("--outdir", default=".",
                    help="Çıktı dosyalarının (tree.json, variations.pgn) yazılacağı klasör")
    p.add_argument("--taraf", choices=["beyaz", "siyah"], default=None,
                    help="Hangi renk için çalışıyorsun (sadece etiket/PGN başlığı için, hesaplamayı değiştirmez)")
    p.add_argument("--dil", choices=["tr", "en"], default=None,
                    help="Arayüz dili. Verilmezse ortam/sistem ayarı, sonra 'tr' kullanılır.")
    p.add_argument("--motor", default=None,
                    help="Kullanılacak motor binary yolu (config'teki engine_path'i geçersiz kılar)")
    p.add_argument("--motor-ekle", dest="motor_ekle", metavar="URL", default=None,
                    help="Verilen URL'den bir motor binary'si indirip yerel olarak kaydeder, sonra çıkar "
                         "(analiz çalıştırmaz)")
    p.add_argument("--motor-isim", dest="motor_isim", default=None,
                    help="--motor-ekle ile birlikte kullanılır: kaydedilecek dosya adı")
    return p.parse_args()


def main():
    args = parse_args()
    lang = get_language(args.dil)

    if args.motor_ekle:
        add_engine(args.motor_ekle, args.motor_isim, lang)
        return

    config_path = resolve_config_path(args, lang)
    cfg = load_config(config_path)
    if args.motor:
        cfg["engine_path"] = args.motor
    os.makedirs(args.outdir, exist_ok=True)

    opening_moves_san = args.opening.split()
    board = chess.Board()
    for san in opening_moves_san:
        board.push_san(san)

    print(f"{t(lang, 'start')}: {' '.join(opening_moves_san)}  FEN={board.fen()}")
    print(t(lang, "config_line", multipv=cfg["multipv"], max_ply=cfg["max_ply"],
             time=cfg["time_per_node_seconds"]))
    if args.taraf:
        print(t(lang, "side_line", side=SIDE_DISPLAY.get(lang, SIDE_DISPLAY["tr"])[args.taraf]))
    print()

    t0 = time.time()
    with chess.engine.SimpleEngine.popen_uci(cfg["engine_path"]) as engine:
        engine.configure({"Threads": cfg["threads"], "Hash": cfg["hash_mb"]})
        tree = build_tree(engine, board, cfg, cfg["max_ply"], lang=lang)
    elapsed = time.time() - t0
    print(f"\n{t(lang, 'total_time')}: {elapsed:.1f} sn")

    tree_path = os.path.join(args.outdir, "tree.json")
    with open(tree_path, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)

    # PGN export
    game = chess.pgn.Game()
    game.headers["Event"] = f"PlyC - {args.opening}"
    if args.taraf:
        game.headers["Taraf" if lang == "tr" else "Side"] = SIDE_DISPLAY.get(lang, SIDE_DISPLAY["tr"])[args.taraf]
    setup_board = chess.Board()
    node = game
    for san in opening_moves_san:
        mv = setup_board.push_san(san)
        node = node.add_variation(mv)
    tree_to_pgn(tree, board.copy(), node, cfg, opening_moves_san, lang=lang)

    pgn_path = os.path.join(args.outdir, "variations.pgn")
    with open(pgn_path, "w", encoding="utf-8") as f:
        print(game, file=f)

    print(f"\n{t(lang, 'outputs_written')}: {tree_path}, {pgn_path}")


if __name__ == "__main__":
    main()
