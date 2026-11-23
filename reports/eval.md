# Evaluation report

Embedder: `hashing`, extractor: `regex`. 30 datasheets, 18 labelled competitor products.

## Extraction

**219/219 fields correct (100.0%)**

| Field | Accuracy |
|---|---|
| type | 100% |
| circuit | 100% |
| mounting | 100% |
| displacement | 100% |
| max_pressure | 100% |
| cont_pressure | 100% |
| max_speed | 100% |
| weight | 100% |
| size | 100% |
| max_flow | 100% |

## Matching

| Mode | Top-1 | Top-3 | MRR | Hard cases |
|---|---|---|---|---|
| naive | 83.3% | 100.0% | 0.917 | 1/4 |
| semantic | 50.0% | 94.4% | 0.727 | 4/4 |
| rules | 100.0% | 100.0% | 1.000 | 4/4 |
| rules+semantic | 100.0% | 100.0% | 1.000 | 4/4 |

## Retrieval (RAG)

| Mode | Hit@3 |
|---|---|
| vector | 93.8% |
| keyword | 100.0% |
| hybrid | 100.0% |

## Matching misses

**naive**
- VT-AX45CL: expected OW-A45C, got OW-A45
- VT-G19: expected OW-G16, got OW-G22
- VT-D6: expected OW-D6H, got OW-D6

**semantic**
- NH-P48: expected OW-A45, got OW-A28
- NH-P74: expected OW-A71, got OW-A100
- NH-V03: expected OW-D6, got OW-D6H
- NH-V05: expected OW-D10, got OW-D6H
- VT-AX45: expected OW-A45, got OW-A28
- VT-G22: expected OW-G22, got OW-G16
- CF-AP71: expected OW-A71, got OW-A100
- CF-GP8: expected OW-G8, got OW-G16
- CF-GP32: expected OW-G32, got OW-G16
