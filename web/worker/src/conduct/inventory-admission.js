// The existing governor owns this gate. Agent task fields are never inventory
// authority; installation of an authenticated canonical adapter is still open.
function routineGeneration(task) {
  const labels = Array.isArray(task?.labels) ? new Set(task.labels) : new Set();
  return /^(GEN-|BLD-|BLD2-)/.test(String(task?.id || ""))
    || (labels.has("generated") && labels.has("build-out"));
}

export function inventoryAdmissionDenied(prior, candidate) {
  return (prior == null || prior.status === "open")
    && ["dispatched", "in_progress"].includes(candidate.status)
    && (routineGeneration(prior) || routineGeneration(candidate));
}

export function inventoryClassificationChanged(prior, candidate) {
  return routineGeneration(prior) && !routineGeneration(candidate);
}
