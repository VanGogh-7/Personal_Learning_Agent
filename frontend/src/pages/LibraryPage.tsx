import BookLibraryPanel from "../components/BookLibraryPanel";

export default function LibraryPage() {
  return (
    <div className="page-stack">
      <section className="page-intro">
        <p>
          Register books and learning materials as metadata. Local paths can be opened from the
          Tauri desktop app with the system default application.
        </p>
      </section>
      <BookLibraryPanel />
    </div>
  );
}
