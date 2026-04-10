const API_BASE = "/api";

async function apiRequest(method, path, body = null) {
  const token = localStorage.getItem("token");
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const options = { method, headers };
  if (body !== null) options.body = JSON.stringify(body);

  const response = await fetch(`${API_BASE}${path}`, options);

  if (response.status === 401) {
    // On the login/register page, let the error bubble up so the form can show it.
    // Anywhere else, the token is expired/invalid — clear it and redirect.
    const isAuthPage = window.location.pathname === "/index.html" || window.location.pathname === "/";
    if (!isAuthPage) {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = "/index.html";
      return;
    }
    let errData;
    try { errData = await response.json(); } catch { errData = {}; }
    throw new Error(errData.detail || "Invalid email or password");
  }

  if (response.status === 204) return null;

  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Server error (${response.status}): ${response.statusText}`);
  }

  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }

  return data;
}

const api = {
  get:    (path)        => apiRequest("GET",    path),
  post:   (path, body)  => apiRequest("POST",   path, body),
  put:    (path, body)  => apiRequest("PUT",    path, body),
  patch:  (path, body)  => apiRequest("PATCH",  path, body),
  delete: (path)        => apiRequest("DELETE", path),
};
