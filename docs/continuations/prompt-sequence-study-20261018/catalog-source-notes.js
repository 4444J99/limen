// Provenance labels are separate from the immutable captured dataset.
const sourceNotes = __SOURCE_NOTES__;
for (const note of sourceNotes) {
  const session = data.sessions.find(item => item.id === note.id);
  if (!session) throw new Error("Source-note session is absent");
  session.alias = note.alias;
  session.annotations ||= [];
  for (const position of note.positions) {
    if (!Number.isInteger(position) || position < 2 || position > session.prompts.length) {
      throw new Error("Source-note position is outside the captured sequence");
    }
    session.annotations[position - 2] = note.label;
  }
}
