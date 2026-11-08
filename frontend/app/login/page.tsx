export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <h1 className="text-2xl font-semibold">Sign in</h1>
      <p className="text-slate-500">Authentication lands in Phase 1.</p>
      <div className="flex gap-4">
        <a
          href="/student"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Student portal
        </a>
        <a
          href="/faculty"
          className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900"
        >
          Faculty portal
        </a>
      </div>
    </main>
  );
}
