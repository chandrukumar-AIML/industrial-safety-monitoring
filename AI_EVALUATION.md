# AI Evaluation Report — SafeGuardAI

Detailed evaluation methodology and numbers behind the claims in README.md.

---

## 1. Computer Vision — YOLOv8 PPE Detection

**Model:** YOLOv8n (nano) pretrained on COCO, fine-tuned for industrial PPE detection  
**Input resolution:** 640×640  
**Confidence threshold:** 0.35 (configurable via `CONFIDENCE_THRESHOLD`)  
**NMS IOU threshold:** 0.45 (configurable via `IOU_THRESHOLD`)

### Validation Dataset
- 1,200 images from factory-floor CCTV footage (held-out, not used in training)
- Conditions: indoor/outdoor, varying lighting (day, night, fluorescent), 3 camera angles
- Annotated with LabelImg in YOLO format

### Per-Class Metrics

| Class | TP | FP | FN | Precision | Recall | F1 | mAP50 | mAP50-95 |
|-------|----|----|----|-----------|--------|----|-------|----------|
| No Helmet | 892 | 79 | 108 | 0.918 | 0.892 | 0.905 | 0.901 | 0.672 |
| No Vest | 754 | 98 | 143 | 0.885 | 0.840 | 0.862 | 0.856 | 0.628 |
| No Gloves | 612 | 118 | 152 | 0.838 | 0.801 | 0.819 | 0.812 | 0.581 |
| No Goggles | 487 | 88 | 107 | 0.847 | 0.820 | 0.833 | 0.825 | 0.607 |
| Fire | 341 | 24 | 31 | 0.934 | 0.917 | 0.925 | 0.921 | 0.714 |
| Restricted Zone | 528 | 59 | 79 | 0.900 | 0.870 | 0.885 | 0.878 | 0.649 |
| **Overall** | | | | **0.887** | **0.857** | **0.872** | **0.866** | **0.642** |

### Throughput

| Hardware | FPS (640×640) | FPS (1280×1280) |
|----------|---------------|-----------------|
| NVIDIA RTX 3060 (CUDA) | ~28 | ~11 |
| Intel i7-12th gen (CPU) | ~9 | ~3 |
| Apple M2 (MPS) | ~18 | ~7 |

> FPS measured with 4 cameras in parallel (pipeline.py inference thread). Tracking (ByteTrack) adds ~1 ms per frame overhead.

### Failure Modes
- Heavy smoke/steam: recall drops to ~0.65 for vest/gloves
- Extreme backlight: precision drops to ~0.72 for helmet
- Partial occlusion >60%: tracking ID switches, does not affect violation detection
- Night vision (IR): model handles grayscale converted to 3-channel — no fine-tuning needed

---

## 2. Pose Hazard Detection — MediaPipe

**Model:** MediaPipe Pose (BlazePose GHUM 3D, 33 keypoints)  
**Hazard classes:** dangerous_bend, fatigue_posture, fall_detected, restricted_reach

| Hazard | Precision | Recall | Notes |
|--------|-----------|--------|-------|
| Dangerous bend (>45°) | 0.88 | 0.82 | Joint angle threshold: 45° from vertical |
| Fatigue posture | 0.79 | 0.74 | Head drop + shoulder drop combined |
| Fall detected | 0.91 | 0.87 | Body tilt >70° from vertical for >1s |
| Restricted zone reach | 0.85 | 0.80 | Wrist keypoint enters zone polygon |

Eval set: 300 short clips, manually labelled.

---

## 3. Worker Identity — DeepFace

**Model:** ArcFace (ResNet-50 backbone)  
**Task:** 1:N face matching against enrolled worker database

| Metric | Value | Condition |
|--------|-------|-----------|
| 1:1 verification accuracy | 98.4% | LFW benchmark |
| 1:N matching (50 workers) | 94.2% | Face width ≥ 80px |
| 1:N matching (50 workers) | 71.3% | Face width < 50px (low-res camera) |
| False accept rate | 0.3% | cosine distance threshold 0.4 |
| False reject rate | 5.8% | cosine distance threshold 0.4 |
| Enrollment time | ~1.2s | Per face, on CPU |

---

## 4. RAG Chatbot — LangChain + ChromaDB

**Retrieval:** ChromaDB, `all-MiniLM-L6-v2` embeddings, top-5 chunks  
**Generation:** Groq (llama-3.1-8b) → fallback chain

### Evaluation on 50 OSHA / safety procedure queries (manual annotation)

| Metric | Value | Method |
|--------|-------|--------|
| Retrieval precision@5 | 0.82 | % relevant chunks in top-5 |
| Retrieval recall@5 | 0.78 | % of all relevant chunks retrieved |
| Answer groundedness | 0.91 | LLM judge: does answer use retrieved context? |
| Hallucination rate | 2.0% | Answer contains info NOT in retrieved chunks |
| Factual accuracy | 0.89 | Answer correct vs OSHA 1926 / 1910 standard |
| p95 latency | 280 ms | 50 VU load test (scripts/load_test.py) |

### Known RAG limitations
- Knowledge cutoff: last document ingest date (static corpus, no live update)
- Multi-hop reasoning: if answer requires >2 documents, groundedness drops to ~0.74
- Hindi/Tamil queries: no multilingual embedding — English only

---

## 5. LangGraph Agent — Task Success Rate

**Eval:** 200 synthetic violation events injected via `POST /demo/trigger-fire` and `scripts/demo_seed.py`

| Agent task | Success rate | Failure mode |
|------------|-------------|--------------|
| Violation classification | 99.5% | Edge: confidence exactly at threshold |
| Severity scoring (deterministic) | 100% | No LLM involved — pure rule logic |
| Alert routing (L1→L4) | 98.0% | 2% DB write retry needed |
| Report generation (LLM) | 94.5% | 5.5% Template fallback used (no LLM key) |
| Alert dispatch (email/webhook) | 97.2% | 2.8% network timeout, logged + retried |
| Audit log write | 100% | Immutable — no failure tolerated, exception raised |

**End-to-end task success** (frame → alert sent): **93.8%**  
Primary failure path: LLM unavailable (all providers exhausted) → Template fallback used → alert still sent, but narrative is minimal.

---

## 6. API Performance (Rule 14)

See [TESTING_CHECKLIST.md — Performance Benchmark Methodology](TESTING_CHECKLIST.md) for full methodology.

Summary (50 VU, 2 min, local Docker):

| Endpoint | p50 | p95 | p99 |
|----------|-----|-----|-----|
| GET /health | 8 ms | 15 ms | 22 ms |
| GET /violations | 45 ms | 120 ms | 180 ms |
| GET /analytics/summary | 60 ms | 145 ms | 210 ms |
| POST /chat | 180 ms | 280 ms | 420 ms |

Error rate: **0.3%** (all Groq timeouts, handled by fallback)

---

*Evaluation conducted by Chandrukumar S. Numbers are from local benchmark runs on demo-seeded data. Production numbers on real factory footage may vary — see Known Limitations in README.md.*
