export default function NotesPage() {
  return (
    <div className="page-stack">
      <section className="page-intro">
        <p>
          A future workspace for LaTeX notes, study summaries, and exports connected to the
          learning chat.
        </p>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>LaTeX Notes Workspace</h2>
            <p>Placeholder for a later notes workflow.</p>
          </div>
        </div>

        <div className="notes-placeholder">
          <div>
            <h3>Future features</h3>
            <ul className="plain-list">
              <li>Generate notes from chat sessions.</li>
              <li>Save and export `.tex` files.</li>
              <li>Organize study notes by topic or book.</li>
              <li>Open notes in an editor in a later desktop stage.</li>
            </ul>
          </div>
          <p className="empty-state">
            Notes are not stored, compiled, previewed, or written to disk in this stage.
          </p>
        </div>
      </section>
    </div>
  );
}
