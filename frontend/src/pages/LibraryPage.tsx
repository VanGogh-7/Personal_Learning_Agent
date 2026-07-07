import BookLibraryPanel from "../components/BookLibraryPanel";

export default function LibraryPage() {
  return (
    <div className="page-stack">
      <section className="page-intro">
        <p>
          Register PDF books as metadata. Local PDF paths can be opened from the Tauri desktop
          app with the system default application.
        </p>
      </section>
      <BookLibraryPanel />
    </div>
  );
}
