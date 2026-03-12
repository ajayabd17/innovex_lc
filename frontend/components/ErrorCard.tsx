import { ApiError } from "@/lib/api";

export function ErrorCard({ error }: { error: unknown }) {
  if (!error) return null;

  let code = "INTERNAL_ERROR";
  let message = "Something went wrong";

  if (error instanceof ApiError) {
    code = error.code;
    message = error.message;
  } else if (error instanceof Error) {
    if (error.message.toLowerCase().includes("failed to fetch")) {
      code = "BACKEND_UNREACHABLE";
      message = "Cannot reach backend API. Check backend server and CORS settings.";
    } else {
      message = error.message;
    }
  }

  return (
    <div className="card border-red-200 bg-red-50">
      <p className="text-xs font-semibold text-red-700">{code}</p>
      <p className="text-sm text-red-700">{message}</p>
    </div>
  );
}
