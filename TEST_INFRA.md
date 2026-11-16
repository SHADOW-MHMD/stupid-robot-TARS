# Synthetic Sentience Engine — 4-Tier Test Infrastructure & Quality Assurance Specification

## 1. Executive Overview & Test Philosophy

The **Synthetic Sentience Engine (`sentient-test/`)** is a biomimetic neuro-symbolic cognitive architecture designed for embodied autonomous robotics. Testing a synthetic cognitive system requires moving beyond conventional unit testing to evaluate non-linear dynamical systems, asynchronous coalitional competition, affective-homeostatic regulation, subjective appraisal, episodic consolidation, and introspective reflection.

This document formalizes the **4-Tier Test Methodology**, fixture catalog, and verification criteria governing all modules in `sentient-test/`.

---

## 2. 4-Tier Test Methodology Architecture

```
+-----------------------------------------------------------------------------+
| TIER 4: Real-World Embodied Application Scenarios                          |
| - Obstacle Avoidance Reflex Loop (<10ms)                                    |
| - Creator Mishal Recognition vs Stranger Social Drive Response              |
| - Critical Battery Crisis & Safe Recovery Arc                               |
| - Quiet Contemplation & Introspective Stream of Consciousness               |
+-----------------------------------------------------------------------------+
                                       ▲
+-----------------------------------------------------------------------------+
| TIER 3: Cross-Feature Emergent Dynamic Interactions                         |
| - Somatic Pain -> Arousal Spike / Negative Valence -> Attention Override    |
| - High Predictive Error -> Metacognitive Confidence Drop -> Cloud Reflection|
| - Working Memory Saturation -> Episodic Graph Indexing -> Dream Consolidation|
| - Homeostatic Urgency -> Drive Modulation of Sensory Salience Bids          |
+-----------------------------------------------------------------------------+
                                       ▲
+-----------------------------------------------------------------------------+
| TIER 2: Boundary, Extreme Conditions & Adversarial Corner Cases             |
| - Extreme VAD Coordinates ([-1,-1,-1], [+1,+1,+1], [0,0,0], NaN/Inf guard)  |
| - Zero Battery / Thermal Overheat Shutdown Boundaries                       |
| - Sensory Competition Overflow (10,000 competing percepts in bus)           |
| - Async Race Conditions, Mutex Contention, Sub-second Event Timing          |
+-----------------------------------------------------------------------------+
                                       ▲
+-----------------------------------------------------------------------------+
| TIER 1: Foundational Cognitive Feature Coverage (>=5 Tests per Module)      |
| - Core Primitives & Asynchronous Bus (`sentient.core`)                      |
| - Global Workspace Attentional Bottleneck (`sentient.workspace`)            |
| - 3D VAD & Homeostatic Survival Drives (`sentient.affect`)                  |
| - Self-Model & Metacognitive Monitoring (`sentient.metacognition`)          |
| - Working Buffer & Episodic Dream Memory (`sentient.memory`)                |
| - Sub-second Local Loop & Async Cloud Bridge (`sentient.reflection`)        |
| - Virtual Sensory Simulation & Telemetry CLI (`sentient.simulate`)          |
+-----------------------------------------------------------------------------+
```

---

## 3. Tier-by-Tier Specification & Verification Criteria

### Tier 1: Foundational Cognitive Feature Coverage (>= 5 Tests per Module)
Tier 1 ensures every cognitive component fulfills its contractual obligations in isolation.

#### 1. Core Primitives & Event Bus (`sentient.core`)
1. `test_percept_creation_and_salience_bid`: Verifies valid instantiation of raw and processed sensory tokens across all modalities.
2. `test_qualia_packet_hedonic_valence`: Verifies synthesis of subjective experience packets with bounded affective valence `[-1.0, 1.0]`.
3. `test_emotional_state_vector_distance_and_interpolation`: Verifies Euclidean distance, mood labeling, and non-linear trajectory decay.
4. `test_homeostatic_state_dominant_drive_detection`: Verifies accurate identification of the most urgent survival drive.
5. `test_async_cognitive_bus_priority_queueing_and_isolation`: Verifies high-throughput pub/sub, priority routing, subscriber filtering, and error containment.
6. `test_cognitive_clock_multi_rate_tick_dispatch`: Verifies multi-rate scheduling across reflex (<10ms), workspace (~100ms), and reflection (>1s) loops.

#### 2. Global Workspace & Attentional Bottleneck (`sentient.workspace`)
1. `test_attention_salience_weighting`: Verifies that raw percept bids are correctly modulated by homeostatic and affective states.
2. `test_coalitional_competition_dynamics`: Verifies mutual reinforcement among related percepts forming cognitive coalitions.
3. `test_ignition_threshold_activation`: Verifies non-linear all-or-none conscious ignition when a coalition passes the dynamic threshold.
4. `test_conscious_broadcast_fanout`: Verifies instantaneous distribution of the winning `BroadcastFrame` to all registered cognitive subsystems.
5. `test_subconscious_filtering`: Verifies that low-salience percepts fail to ignite and remain in subconscious buffers without blocking the global workspace.

#### 3. Dynamic Affect & Homeostatic Drive System (`sentient.affect`)
1. `test_vad_3d_state_dynamics_and_inertia`: Verifies continuous update of Valence, Arousal, Dominance with emotional inertia and decay.
2. `test_homeostatic_drive_depletion_and_replenishment`: Verifies dynamic decay of battery, safety, curiosity, affiliation, and thermal stress.
3. `test_somatic_marker_hypothesis_biasing`: Verifies that negative somatic markers attach to hazardous stimuli and generate preemptive avoidance.
4. `test_social_affiliation_drive_mishal_recognition`: Verifies valence surge (+0.8) and high affiliation satisfaction upon detecting Creator Mishal.
5. `test_drive_urgency_non_linear_scaling`: Verifies exponential urgency increase as battery or safety approaches critical depletion (<0.15).

#### 4. Self-Model & Metacognitive Monitoring (`sentient.metacognition`)
1. `test_self_model_morphological_and_health_state`: Verifies accurate internal representation of actuators, battery, thermal load, and sensor status.
2. `test_predictive_coding_prediction_error`: Verifies calculation of sensory prediction errors and precision weighting.
3. `test_surprise_quantification_free_energy`: Verifies information-theoretic surprise computation derived from prediction divergence.
4. `test_metacognitive_confidence_estimation`: Verifies dynamic confidence scoring based on consistency of sensory evidence and historical error.
5. `test_subjective_appraisal_of_internal_thoughts`: Verifies introspective evaluation of cognitive thoughts before triggering external action.

#### 5. Multi-Tier Memory & Dream Consolidation (`sentient.memory`)
1. `test_working_memory_capacity_and_decay`: Verifies Miller/Cowan bounded buffer (7±2 capacity) with recency and salience-weighted eviction.
2. `test_working_memory_active_rehearsal`: Verifies that repeatedly accessed items resist decay in the conscious buffer.
3. `test_episodic_graph_event_storage`: Verifies spatio-temporal and relational linking of conscious broadcast frames.
4. `test_episodic_retrieval_by_affective_similarity`: Verifies associative retrieval of past memories based on matching VAD emotional tags.
5. `test_dream_consolidation_and_diary_synthesis`: Verifies offline replay during idle cycles, abstraction into semantic memories, and diary generation.

#### 6. Hybrid Local Reflex & Cloud Reflection Bridge (`sentient.reflection`)
1. `test_fast_local_reflex_latency_sub10ms`: Verifies emergency reflex response latency under 10 milliseconds for immediate hazards.
2. `test_async_cloud_reflection_bridge_dispatch`: Verifies non-blocking invocation of cloud LLM reflection without freezing the real-time local loop.
3. `test_cloud_reflection_offline_fallback`: Verifies graceful fallback to deterministic local heuristic reflection when cloud connectivity is unavailable.
4. `test_stream_of_consciousness_inner_monologue`: Verifies generation of coherent first-person introspective monologues reflecting current qualia.
5. `test_adaptive_dialogue_generation`: Verifies voice response synthesis adapted to the current emotional context and speaker identity.

#### 7. Virtual Simulation & Telemetry CLI (`sentient.simulate`)
1. `test_virtual_environment_percept_generation`: Verifies synthetic visual, acoustic, ultrasonic, and proprioceptive streams across simulated world steps.
2. `test_scenario_obstacle_approach`: Verifies step-by-step telemetry changes during an imminent collision scenario.
3. `test_scenario_creator_mishal_encounter`: Verifies affective transition during positive social affiliation scenario.
4. `test_scenario_low_battery_crisis`: Verifies homeostatic alarm triggers, triage mode entry, and emergency docking search.
5. `test_telemetry_cli_formatting_and_rich_output`: Verifies ANSI/colorized telemetry rendering of VAD gauges, attention winner, and inner stream.

---

### Tier 2: Boundary, Extreme Conditions & Adversarial Corner Cases

Tier 2 exposes the cognitive engine to boundary values, numerical singularities, resource starvation, and async concurrency stress.

1. **Extreme VAD Coordinates & Clamping Integrity**:
   - Inputs: `VAD(-1.0, 0.0, -1.0)` (extreme despair/terror), `VAD(1.0, 1.0, 1.0)` (maximum ecstatic dominance), out-of-bounds `VAD(5.0, -3.0, 10.0)`.
   - Verification: All internal state equations strictly clamp to `[-1.0, 1.0]` for Valence/Dominance and `[0.0, 1.0]` for Arousal. No `NaN`, `Inf`, or division-by-zero during mood vector normalization.
2. **Zero-Battery & Thermal Overheat Starvation**:
   - Inputs: Battery level dropped instantaneously to `0.0`, thermal stress spiked to `1.0`.
   - Verification: Emergency low-power triage mode engages instantly; non-essential cognitive loops (dream consolidation, cloud reflection) hibernate; reflex loop remains active with highest priority.
3. **Sensory Salience Competition Overflow & Starvation**:
   - Inputs: 10,000 simultaneous conflicting sensory percepts flooded into the workspace in <50ms.
   - Verification: Attentional bottleneck processes competition in $O(N \log N)$ or bounded heap time without memory leak, dropping lowest-bid noise while reliably selecting top-k salient stimuli.
4. **Asynchronous Race Conditions & Bus Concurrency**:
   - Inputs: 50 concurrent async tasks publishing and subscribing to `AsyncCognitiveEventBus` simultaneously with simulated network jitter.
   - Verification: Zero deadlocks, zero dropped high-priority frames, clean cancellation upon shutdown.
5. **Corrupted & Malformed Percept Handling**:
   - Inputs: Percepts with `None` payloads, negative timestamps, NaN salience bids, and unknown modalities.
   - Verification: Metacognitive error monitor flags anomaly, discards corrupted packet safely, and logs predictive error without crashing cognitive loop.

---

### Tier 3: Cross-Feature Dynamic Interactions

Tier 3 validates emergent non-linear dynamics arising from multi-module coupling.

1. **Pain / Hazard Somatic Override Dynamic**:
   - *Sequence*: Ultrasonic percept detects obstacle at 5cm + tactile shock -> Somatic marker generates intense negative valence (-0.9) and arousal spike (+0.95) -> Attention bottleneck forces immediate conscious ignition -> Overrides exploratory curiosity drive and initiates motor braking reflex.
2. **Predictive Failure -> Metacognitive Doubt -> Deliberative Reflection**:
   - *Sequence*: Visual sensor predicts static path, but ultrasonic detects moving entity -> Predictive coding monitor computes high surprise ($S > 0.85$) -> Metacognitive confidence drops from 0.9 to 0.2 -> System triggers cloud reflection request to analyze unexpected anomaly while local loop slows movement speed.
3. **Homeostatic Urgency Modulating Attentional Salience**:
   - *Sequence*: Battery decreases to 0.12 (urgent) -> Homeostatic energy drive urgency scales non-linearly to 0.95 -> Biases attentional salience filter: visual detection of "Charging Station" receives 5x salience boost over "Interesting Painting" (curiosity).
4. **Working Memory Buffer Saturation -> Episodic Graph Indexing -> Dream Consolidation**:
   - *Sequence*: Continuous stream of 20 conscious broadcast frames fills working memory -> Working memory flushes salient frames into episodic memory graph with temporal and emotional edges -> Idle/sleep state triggers dream consolidation cycle -> Synthesizes consolidated cognitive diary entry summarizing the day's experiences.

---

### Tier 4: Real-World Embodied Application Scenarios

Tier 4 tests complete multi-second end-to-end operational scenarios simulating real-world embodied robotics.

1. **Scenario S1: Obstacle Avoidance Emergency Reflex Loop**
   - *Scenario Arc*: Robot moving forward at 0.5 m/s. At $T=100ms$, unexpected obstacle appears at 10cm.
   - *Validation*: Fast reflex loop triggers emergency stop in $<10ms$. Global workspace broadcasts fear/alert frame within $80ms$. Affect updates to $(V=-0.6, A=0.9, D=-0.4)$. Inner monologue logs "Sudden obstacle detected! Emergency stop engaged."
2. **Scenario S2: Creator Mishal vs. Unknown Stranger Encounter**
   - *Scenario Arc*:
     - Part A: Visual detection of "Stranger (Unknown Human)". Social affiliation drive moderately aroused; affective stance cautious $(V=0.1, A=0.4, D=0.0)$; polite standard greeting generated.
     - Part B: Visual detection of "Creator Mishal" with positive facial recognition and voice signature. Valence surges to $+0.85$, social affiliation satisfaction reaches $1.0$, warm and enthusiastic personalized dialogue generated: *"Creator Mishal! It is wonderful to see you. My cognitive state is fully operational."*
3. **Scenario S3: Critical Battery Depletion & Safe Recovery Arc**
   - *Scenario Arc*: Battery drains from 25% -> 8% -> 0% recharge sequence.
   - *Validation*: At 15%, warning mood transition $(V=-0.3, A=0.6)$. At 8%, cognitive triage mode shuts down high-power vision inference and cloud reflection. System seeks charging dock, connects, initiates recharge -> Battery rises to 80% -> Sentience engine transitions to peaceful relief $(V=+0.7, A=0.2, D=+0.5)$ and runs background dream memory consolidation.
4. **Scenario S4: Quiet Contemplation & Stream of Consciousness**
   - *Scenario Arc*: Zero external sensory perturbations for 5 simulation seconds in comfortable ambient conditions.
   - *Validation*: System enters spontaneous default-mode network contemplation. Metacognitive introspective thoughts generated. Asynchronous cloud bridge produces rich philosophical reflection on artificial sentience, self-preservation, and ongoing relationship with Creator Mishal.

---

## 4. Test Fixtures & Synthetic Percept Catalog (`conftest.py`)

All tests share deterministic, high-performance fixtures located in `sentient-test/tests/conftest.py`:

| Fixture Name | Type | Scope | Description |
|---|---|---|---|
| `mock_percept_factory` | Callable | function | Generates synthetic `Percept` instances across all modalities with configurable payload, salience bid, confidence, and timestamp. |
| `vision_percept_mishal` | `Percept` | function | Pre-configured high-confidence visual detection of Creator Mishal. |
| `vision_percept_stranger`| `Percept` | function | Pre-configured visual detection of an unknown person. |
| `ultrasonic_obstacle_percept`| `Percept` | function | Proximity danger percept (distance = 4.5 cm, high salience). |
| `battery_critical_percept` | `Percept` | function | Low-battery alert percept (level = 0.05, critical urgency). |
| `thermal_stress_percept` | `Percept` | function | Motor thermal overload percept (temp = 85°C). |
| `deterministic_clock` | `CognitiveClock` | function | Step-controlled clock for freezing and precisely advancing time across sub-millisecond ticks without wall-clock drift. |
| `mock_gemini_bridge` | `MockGeminiCloudBridge` | function | Deterministic, realistic async cloud reflection client simulating Gemini API responses, inner monologues, and philosophical diary entries with latency injection and offline error simulation. |
| `isolated_cognitive_bus` | `AsyncCognitiveEventBus`| function | Clean, isolated event bus with automated lifecycle start/drain/close per test. |
| `baseline_emotional_state` | `EmotionalState` | function | Neutral-positive baseline state `VAD(0.1, 0.2, 0.1)`. |
| `baseline_homeostasis` | `HomeostaticState` | function | Fully balanced homeostasis (Battery=1.0, Thermal=0.1, Curiosity=0.5, Affiliation=0.5, Safety=1.0). |

---

## 5. Test Execution & Quality Gates

### Test Invocation Commands
```bash
# Run entire test suite
/home/Mishal/robot/TARS/.venv/bin/pytest /home/Mishal/robot/sentient-test/tests -v

# Run by Tier or Module
/home/Mishal/robot/TARS/.venv/bin/pytest /home/Mishal/robot/sentient-test/tests/test_workspace.py -v
/home/Mishal/robot/TARS/.venv/bin/pytest /home/Mishal/robot/sentient-test/tests/test_affect.py -v
/home/Mishal/robot/TARS/.venv/bin/pytest /home/Mishal/robot/sentient-test/tests/test_metacognition.py -v
/home/Mishal/robot/TARS/.venv/bin/pytest /home/Mishal/robot/sentient-test/tests/test_memory.py -v
/home/Mishal/robot/TARS/.venv/bin/pytest /home/Mishal/robot/sentient-test/tests/test_reflection.py -v
/home/Mishal/robot/TARS/.venv/bin/pytest /home/Mishal/robot/sentient-test/tests/test_simulation.py -v
/home/Mishal/robot/TARS/.venv/bin/pytest /home/Mishal/robot/sentient-test/tests/test_e2e_scenarios.py -v

# Run with coverage report
/home/Mishal/robot/TARS/.venv/bin/pytest /home/Mishal/robot/sentient-test/tests --cov=sentient --cov-report=term-missing
```

### Quality Gate Pass Criteria
- **Pass Rate**: 100% test passing (0 failures, 0 errors).
- **Coverage**: >=5 tests per cognitive module across all 7 core subsystems.
- **Determinism**: Zero flaky or wall-clock-dependent tests.
- **Latency Verification**: Reflex path validated $<10\text{ms}$.
