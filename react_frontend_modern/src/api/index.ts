// react_frontend_modern/src/api/index.ts
// C'est le VRAI client API pour interagir avec le backend GRA.

declare global { // Assurez-vous que cette déclaration est toujours disponible
  interface Window {
    CONFIG: { BACKEND_API_URL: string };
  }
}

const BACKEND_API_URL = window.CONFIG?.BACKEND_API_URL || 'http://localhost:8000'; // Assure-toi que c'est bien l'URL de ton GRA local

const apiClient = {
  get: async (path: string) => {
    console.log(`Real API Call: GET ${BACKEND_API_URL}${path}`); // Change le log pour le distinguer
    const response = await fetch(`${BACKEND_API_URL}${path}`);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(`HTTP error! Status: ${response.status}, Detail: ${errorData.detail}`);
    }
    return response.json();
  },
  post: async (path: string, data: any) => {
    console.log(`Real API Call: POST ${BACKEND_API_URL}${path}`, data); // Change le log
    const response = await fetch(`${BACKEND_API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(`HTTP error! Status: ${response.status}, Detail: ${errorData.detail}`);
    }
    return response.json();
  },
  put: async (path: string, data: any) => {
    console.log(`Real API Call: PUT ${BACKEND_API_URL}${path}`, data); // Change le log
    const response = await fetch(`${BACKEND_API_URL}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(`HTTP error! Status: ${response.status}, Detail: ${errorData.detail}`);
    }
    return response.json();
  },
  delete: async (path: string) => {
    console.log(`Real API Call: DELETE ${BACKEND_API_URL}${path}`); // Change le log
    const response = await fetch(`${BACKEND_API_URL}${path}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(`HTTP error! Status: ${response.status}, Detail: ${errorData.detail}`);
    }
    return response.json();
  },
};

export default apiClient;