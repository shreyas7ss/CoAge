import type { ApiError, Assignment, Course, Evaluation, EvaluationDetail, Followup, Submission } from "./types";

const prefix = "/api/backend";
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${prefix}${path}`, {
    ...init,
    headers: { ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export const apiPaths = {
  courses: () => api<Course[]>("/courses"),
  assignments: (courseId: string) => api<Assignment[]>(`/courses/${courseId}/assignments`),
  submissions: () => api<Submission[]>("/me/submissions"),
  followups: () => api<Followup[]>("/me/followups"),
  reviewQueue: (courseId: string) => api<Evaluation[]>(`/courses/${courseId}/review-queue`),
  evaluation: (id: string) => api<EvaluationDetail>(`/evaluations/${id}`),
};
