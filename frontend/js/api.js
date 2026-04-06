const API_BASE = "/api";

async function apiRequest(method, path, body = null) {
  const token = localStorage.getItem("token");
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const options = { method, headers };
  if (body !== null) options.body = JSON.stringify(body);

  const response = await fetch(`${API_BASE}${path}`, options);

  if (response.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.location.href = "/index.html";
    return;
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
