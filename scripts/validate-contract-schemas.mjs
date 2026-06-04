#!/usr/bin/env node
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const publicDir = join(root, "web", "app", "public");
const privateDir = join(root, "web", "app", ".generated", "surfaces");
const schemaDir = join(root, "spec", "contracts");

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function fail(message) {
  console.error(`contract schema validation failed: ${message}`);
  process.exit(1);
}

function typeMatches(value, expected) {
  const types = Array.isArray(expected) ? expected : [expected];
  return types.some((type) => {
    if (type === "array") return Array.isArray(value);
    if (type === "null") return value === null;
    if (type === "number") return typeof value === "number" && Number.isFinite(value);
    if (type === "object") return value !== null && typeof value === "object" && !Array.isArray(value);
    return typeof value === type;
  });
}

function resolveRef(schema, ref) {
  if (!ref.startsWith("#/$defs/")) fail(`unsupported ref ${ref}`);
  const name = ref.slice("#/$defs/".length);
  const resolved = schema.$defs?.[name];
  if (!resolved) fail(`missing ref ${ref}`);
  return resolved;
}

function validate(value, node, path, rootSchema) {
  if (node.$ref) {
    validate(value, resolveRef(rootSchema, node.$ref), path, rootSchema);
    return;
  }
  if (node.type && !typeMatches(value, node.type)) {
    fail(`${path} expected ${JSON.stringify(node.type)}, got ${Array.isArray(value) ? "array" : value === null ? "null" : typeof value}`);
  }
  if (node.enum && !node.enum.includes(value)) {
    fail(`${path} expected one of ${node.enum.join(", ")}, got ${value}`);
  }
  if (node.required) {
    for (const key of node.required) {
      if (!Object.prototype.hasOwnProperty.call(value, key)) fail(`${path}.${key} is required`);
    }
  }
  if (node.properties && value && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(node.properties)) {
      if (Object.prototype.hasOwnProperty.call(value, key)) validate(value[key], child, `${path}.${key}`, rootSchema);
    }
    if (node.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        if (!Object.prototype.hasOwnProperty.call(node.properties, key)) {
          fail(`${path}.${key} is not allowed`);
        }
      }
    }
  }
  if (node.items && Array.isArray(value)) {
    value.forEach((item, index) => validate(item, node.items, `${path}[${index}]`, rootSchema));
  }
}

function validateFile(schemaName, jsonName, dir = publicDir) {
  const schema = readJson(join(schemaDir, schemaName));
  const payload = readJson(join(dir, jsonName));
  validate(payload, schema, jsonName, schema);
}

for (const name of ["surface-manifest.json", "public-surface-manifest.json"]) {
  validateFile("surface-manifest.schema.json", name);
}
for (const name of ["client-surface-manifest.json", "owner-surface-manifest.json"]) {
  validateFile("surface-manifest.schema.json", name, privateDir);
}

for (const name of ["public-status.json"]) {
  validateFile("status-summary.schema.json", name);
}
validateFile("pr-status.schema.json", "pr-status.json");
for (const name of ["client-status.json", "internal-status.json"]) {
  validateFile("status-summary.schema.json", name, privateDir);
}

validateFile("qa-status.schema.json", "qa-status.json", privateDir);
validateFile("readiness.schema.json", "readiness.json", privateDir);

console.log("Contract JSON Schemas verified");
