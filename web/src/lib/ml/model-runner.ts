import fs from "fs";
import path from "path";
import { ProcessAnalysisResult, RawProcessRow } from "../types";
import { extractProcessFeatures } from "./feature-extractor";

interface DecisionTreeData {
  children_left: number[];
  children_right: number[];
  feature: number[];
  threshold: number[];
  value: number[];
}

interface ModelPackage {
  version: string;
  model_type: string;
  learning_rate: number;
  init_prior: number[];
  scaler?: {
    mean: number[];
    scale: number[];
    var: number[];
  };
  features: string[];
  classes: string[];
  trees: DecisionTreeData[][];
}

let cachedModel: ModelPackage | null = null;

export function loadModel(): ModelPackage {
  if (cachedModel) return cachedModel;

  const modelPath = path.join(process.cwd(), "public", "models", "keylogger_detector.json");
  if (!fs.existsSync(modelPath)) {
    throw new Error(`Model weights not found at ${modelPath}`);
  }

  const raw = fs.readFileSync(modelPath, "utf-8");
  cachedModel = JSON.parse(raw) as ModelPackage;
  return cachedModel;
}

function evaluateSingleTree(tree: DecisionTreeData, features: number[]): number {
  let node = 0;
  while (tree.children_left[node] !== -1 && tree.children_right[node] !== -1) {
    const featIdx = tree.feature[node];
    const thresh = tree.threshold[node];
    if (features[featIdx] <= thresh) {
      node = tree.children_left[node];
    } else {
      node = tree.children_right[node];
    }
  }
  return tree.value[node];
}

function softmax(logits: number[]): number[] {
  const maxLogit = Math.max(...logits);
  const exps = logits.map((l) => Math.exp(l - maxLogit));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map((e) => e / (sum || 1));
}

export function predictProcess(row: RawProcessRow, model?: ModelPackage): ProcessAnalysisResult {
  const m = model || loadModel();
  const { vector, reasons, isWhitelisted } = extractProcessFeatures(row);

  // Apply StandardScaler
  const scaledFeatures = [...vector];
  if (m.scaler) {
    for (let i = 0; i < scaledFeatures.length; i++) {
      const mean = m.scaler.mean[i] ?? 0;
      const scale = m.scaler.scale[i] || 1;
      scaledFeatures[i] = (scaledFeatures[i] - mean) / scale;
    }
  }

  // Evaluate Gradient Boosting Trees
  const rawScores = [...(m.init_prior || [0, 0, 0])];
  const numStages = m.trees.length;

  for (let stage = 0; stage < numStages; stage++) {
    const stageTrees = m.trees[stage];
    for (let c = 0; c < stageTrees.length; c++) {
      const treeVal = evaluateSingleTree(stageTrees[c], scaledFeatures);
      rawScores[c] += m.learning_rate * treeVal;
    }
  }

  const probs = softmax(rawScores);

  // Map class indices from metadata dynamically
  const classMap: Record<string, number> = {};
  m.classes.forEach((c, idx) => {
    classMap[c.toLowerCase()] = idx;
  });

  const malIdx = classMap["malicious"] ?? 0;
  const safeIdx = classMap["safe"] ?? 1;
  const suspIdx = classMap["suspicious"] ?? 2;

  const malProb = probs[malIdx] ?? 0;
  const safeProb = probs[safeIdx] ?? 0;
  const suspProb = probs[suspIdx] ?? 0;

  // Compute 0-100 risk score
  let riskScore = Math.round((suspProb * 40 + malProb * 100) * 10) / 10;
  
  if (isWhitelisted) {
    riskScore = Math.min(riskScore, 5);
  }

  let classification: "SAFE" | "SUSPICIOUS" | "MALICIOUS" = "SAFE";
  if (riskScore >= 60 || malProb > 0.45) {
    classification = "MALICIOUS";
  } else if (riskScore >= 30 || suspProb > 0.45) {
    classification = "SUSPICIOUS";
  }

  return {
    pid: row.pid ?? Math.floor(1000 + Math.random() * 9000),
    name: row.name,
    riskScore,
    classification,
    probabilities: {
      safe: Math.round(safeProb * 1000) / 1000,
      suspicious: Math.round(suspProb * 1000) / 1000,
      malicious: Math.round(malProb * 1000) / 1000,
    },
    features: vector,
    reasons,
    cpu: row.cpu ?? 0,
    memoryMb: row.memoryMb ?? 0,
    hasWindow: row.hasWindow ?? false,
    isSigned: row.isSigned ?? false,
    path: row.exePath,
  };
}

export function analyzeProcesses(rows: RawProcessRow[]): ProcessAnalysisResult[] {
  const model = loadModel();
  return rows.map((row) => predictProcess(row, model));
}
