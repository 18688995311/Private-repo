import os, re, json, csv, sys
from pathlib import Path
import pandas as pd
import cv2
from paddleocr import PaddleOCR
from rapidfuzz import fuzz

JOB = Path(os.environ.get("JOB","")).expanduser()
assert JOB.exists(), "missing JOB env. export JOB=/tmp/xxx"
IMG_DIR = JOB / "images_760w"
assert IMG_DIR.exists(), f"missing {IMG_DIR}"

OUT_DIR = JOB / "ocr_out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- 你这类复盘表，常见字段关键词（用于判断是否“像表格结果”） ----
KEYWORDS = [
  "代码","名称","涨停","涨停原因","连板","成交额","流通","流通值",
  "游资","买入","卖出","净买","营业部","主力净额","板块","强度",
  "涨幅","得分","收盘价","量比","两市占比","监控开始","监控结束"
]

CODE_PAT = re.compile(r"^(?:SZ|SH)?\s*\d{6}$", re.I)

def normalize(s:str)->str:
    s = (s or "").replace("\u3000"," ").replace("\xa0"," ")
    s = re.sub(r"[ \t]+"," ", s).strip()
    return s

def ocr_image(ocr:PaddleOCR, img_path:Path):
    # 返回：[(text, conf, x0,y0,x1,y1), ...]
    img = cv2.imread(str(img_path))
    if img is None:
        return []
    results = ocr.predict(img)
    blocks = []
    for r in (results or []):
        if not r or "rec_texts" not in r:
            continue
        for txt, conf, pts in zip(r["rec_texts"], r["rec_scores"], r["dt_polys"]):
            if not txt:
                continue
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            blocks.append((normalize(txt), float(conf), int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))))
    # 去掉空
    blocks = [b for b in blocks if b[0]]
    return blocks

def looks_like_table(blocks):
    if not blocks:
        return (False, 0.0, "no_blocks")
    texts = [b[0] for b in blocks]
    joined = " ".join(texts)

    # 关键词命中
    kw_hits = sum(1 for k in KEYWORDS if k in joined)

    # 股票代码命中（6位）
    code_hits = 0
    for t in texts:
        tt = re.sub(r"[^\dA-Za-z]","",t)
        if re.fullmatch(r"(?:SZ|SH)?\d{6}", tt, re.I):
            code_hits += 1
        elif re.fullmatch(r"\d{6}", tt):
            code_hits += 1

    # 行数估计：按 y 分桶
    ys = [b[3] for b in blocks]
    ys_sorted = sorted(ys)
    # 粗略行聚类
    rows = 1
    for i in range(1,len(ys_sorted)):
        if ys_sorted[i] - ys_sorted[i-1] > 14:
            rows += 1

    # 得分：关键词+代码+行数（你这类表格会非常高）
    score = kw_hits*1.2 + min(code_hits,30)*0.7 + min(rows,60)*0.15
    ok = (kw_hits >= 3 and rows >= 8) or (code_hits >= 5 and rows >= 8) or (score >= 12)

    reason = f"kw={kw_hits},code={code_hits},rows~={rows},score={score:.2f}"
    return ok, score, reason

def blocks_to_rows(blocks):
    # 简单按 y 聚类成行，再按 x 排序
    blocks = sorted(blocks, key=lambda b: (b[3], b[2]))
    rows = []
    cur = []
    cur_y = None
    for b in blocks:
        y = b[3]
        if cur_y is None:
            cur_y = y
            cur = [b]
            continue
        if abs(y - cur_y) <= 14:
            cur.append(b)
        else:
            rows.append(sorted(cur, key=lambda x: x[2]))
            cur = [b]
            cur_y = y
    if cur:
        rows.append(sorted(cur, key=lambda x: x[2]))
    # 每行转成 cell 文本
    text_rows = []
    for r in rows:
        text_rows.append([c[0] for c in r])
    return text_rows

def try_struct(text_rows):
    """
    尝试把 OCR 的行列变成一个“表格”：
    - 先找表头行：包含多个关键词
    - 再把后续行按列对齐（用 x 已经做了粗排，仍可能不准）
    返回：
      {type, header, rows, quality}
    """
    if not text_rows:
        return None

    # 找最像表头的一行：关键词命中最多且 cell 数多
    best_i, best_score = -1, -1
    for i,row in enumerate(text_rows[:20]):
        s = " ".join(row)
        kw = sum(1 for k in KEYWORDS if k in s)
        cell_n = len(row)
        sc = kw*3 + min(cell_n,20)
        if sc > best_score:
            best_score = sc; best_i = i

    header = text_rows[best_i]
    header_join = " ".join(header)

    # 简单判断表格类型
    def has(*ks): return all(k in header_join for k in ks)
    if ("游资" in header_join) or has("总买入","总卖出"):
        t = "游资汇总"
    elif ("营业部" in header_join) and ("总买入" in header_join or "总净买" in header_join):
        t = "营业部汇总"
    elif ("板块" in header_join) and ("强度" in header_join or "主力净额" in header_join):
        t = "板块强度"
    elif ("涨停原因" in header_join) and ("连板" in header_join or "成交额" in header_join):
        t = "涨停连板"
    elif ("5日" in header_join) or ("区间" in header_join and "涨幅" in header_join):
        t = "5日涨幅榜"
    elif ("监控开始" in header_join) or ("监控结束" in header_join):
        t = "监控区间"
    else:
        t = "未知表"

    # 数据行
    data_rows = text_rows[best_i+1:]
    # 过滤明显不是行的（太短）
    data_rows = [r for r in data_rows if len(r) >= max(2, min(len(header), 5))]

    # 质量：行数 + “是否出现代码列”
    joined = " ".join([" ".join(r) for r in data_rows[:30]])
    code_hits = len(re.findall(r"\b\d{6}\b", joined))
    quality = (len(data_rows) >= 5) + (code_hits >= 3) + (len(header) >= 5)

    if len(header) < 3 or len(data_rows) < 3:
        return None

    return {"type": t, "header": header, "rows": data_rows, "quality": int(quality)}

def main():
    ocr = PaddleOCR(lang="ch")  # 中文+英文混排，3.x 不再需要 use_angle_cls
    imgs = sorted(IMG_DIR.glob("*.*"))
    merged_records = []
    summary = []

    for p in imgs:
        blocks = ocr_image(ocr, p)
        ok, score, reason = looks_like_table(blocks)

        rec = {"file": p.name, "path": str(p), "is_table": int(ok), "score": float(score), "reason": reason}
        out_json = OUT_DIR / f"{p.stem}.ocr.json"
        out_json.write_text(json.dumps({"meta": rec, "blocks": blocks}, ensure_ascii=False, indent=2), encoding="utf-8")

        if not ok:
            summary.append({**rec, "status":"skip_not_table"})
            continue

        text_rows = blocks_to_rows(blocks)
        st = try_struct(text_rows)
        if not st or st.get("quality",0) < 2:
            summary.append({**rec, "status":"fail_struct"})
            continue

        # 输出结构化表
        table_json = OUT_DIR / f"{p.stem}.table.json"
        table_json.write_text(json.dumps({"meta": rec, **st}, ensure_ascii=False, indent=2), encoding="utf-8")

        # 合并：每行转 dict（列数不齐就截断/补空）
        header = [normalize(x) for x in st["header"]]
        for row in st["rows"]:
            row2 = row[:len(header)] + [""] * max(0, len(header)-len(row))
            merged_records.append({
                "__file": p.name,
                "__type": st["type"],
                **{header[i] if header[i] else f"col_{i+1}": normalize(row2[i]) for i in range(len(header))}
            })

        summary.append({**rec, "status":"ok", "table_type": st["type"], "rows": len(st["rows"]), "cols": len(st["header"])})

    # 输出总结果
    (JOB/"ocr_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if merged_records:
        df = pd.DataFrame(merged_records)
        df.to_csv(JOB/"merged.csv", index=False, encoding="utf-8-sig")
        # jsonl 更适合入库
        with open(JOB/"merged.jsonl","w",encoding="utf-8") as f:
            for r in merged_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("done")
    print("summary:", JOB/"ocr_summary.json")
    print("merged.csv:", JOB/"merged.csv" if merged_records else "none")
    print("merged.jsonl:", JOB/"merged.jsonl" if merged_records else "none")
    print("per-image outputs:", OUT_DIR)

if __name__ == "__main__":
    main()
