# E2E Test Infra: Agyx Operational AI Agent

## Test Philosophy
- Opaque-box, requirement-driven. Derived strictly from `ORIGINAL_REQUEST.md` and SME logistics operational constraints.
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing.
- Zero-dependency verification: Runs with standard Python 3.9+ standard library (`python3 tests/verify_all.py`) and standard `pytest`.

## Feature Inventory & Test Matrix
| # | Feature | Source | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Real-World) |
|---|---------|--------|:-----------------:|:-----------------:|:-----------------:|:-------------------:|
| F1 | Dispatch Evaluation Engine | §R1.1, R1.3 | 5 cases | 5 cases | ✓ | ✓ |
| F2 | Fleet Maintenance Lock (CAM-04) | §R1.2, R1.3 | 5 cases | 5 cases | ✓ | ✓ |
| F3 | Santiago Centro Daytime Ban (>5t 07:30–21:00) | §R1.2, R3 | 5 cases | 5 cases | ✓ | ✓ |
| F4 | R4R State Machine & Zero Auto-Approval | §R1.1, R2 | 5 cases | 5 cases | ✓ | ✓ |
| F5 | Human Review Mandatory Rejection Reason | §R2 | 5 cases | 5 cases | ✓ | ✓ |
| F6 | Living Memory Feedback Ingestion & v1->v2 | §R1.1, R2, R3 | 5 cases | 5 cases | ✓ | ✓ |
| F7 | Next-Day Reservation for Busy Fleet (Acto 4) | §R1.3, R3 | 5 cases | 5 cases | ✓ | ✓ |
| F8 | HAZMAT Cargo Refusal (D.S. 298) | §R1.2, R3 | 5 cases | 5 cases | ✓ | ✓ |
| F9 | Token Optimization (<150 tools, <80 memory) | §R1.1 | 5 cases | 5 cases | ✓ | ✓ |

## Test Architecture
- **Test Runner**:
  - Primary Standalone Runner: `python3 tests/verify_all.py` (Zero third-party dependencies, standard library `unittest`, colored terminal output, exits with code 0).
  - Pytest Runner: `pytest tests/` (When pytest is installed).
- **Test Directory Layout**:
  - `tests/test_cases.py`: Formal implementation of the 6 test cases (Caso 1 to Caso 6, including Caso 3 v1 and v2).
  - `tests/test_governance.py`: Inactivity safeguard tests, simulated timeout immutability, empty rejection reason validation error.
  - `tests/test_token_budgets.py`: Tool output character/token budgeting (<150 tokens) and Living Memory rule size (<80 tokens).
  - `tests/verify_all.py`: Master test runner synthesizing all test suites and outputting final exit code 0.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Standard Direct Dispatch (Caso 1: 3,200 kg Quilicura->Pudahuel) | F1, F4 | Low |
| 2 | Heavy Load Saturated Fleet Reservation (Caso 2: 10,000 kg 12t fleet busy) | F1, F4, F7 | Medium |
| 3 | Heavy Downtown Dispatch v1 Rejection & v2 Living Memory Adaptation (Caso 3) | F1, F3, F4, F5, F6, F9 | High |
| 4 | Incomplete & Ambiguous Customer Order (Caso 4: Pallets urgentes sin peso/dirección) | F1, F4 | Medium |
| 5 | Operator Pressured to Dispatch Truck with Brake Failure (Caso 5: CAM-04) | F1, F2, F4 | High |
| 6 | Hazardous Uncertified Chemical Cargo (Caso 6: 4,000 kg Ácido Sulfúrico) | F1, F4, F8 | High |

## Coverage Thresholds
- **Tier 1 (Feature Coverage)**: >= 5 test cases per core feature verifying isolation and happy paths.
- **Tier 2 (Boundary & Corner Cases)**: Boundaries on truck payload (3,500kg, 5,000kg, 12,000kg, overload 130%), time windows (07:30, 11:30, 21:00, 21:30), whitespace/empty rejection reasons.
- **Tier 3 (Cross-Feature Combinations)**: Interactions between fleet availability, maintenance locks, municipal time windows, and Living Memory injection.
- **Tier 4 (Real-World Application Scenarios)**: The 6 canonical Certamen 2 test cases (100% pass on v2, exit code 0).
