/**
 * GeordieDaz — useAuth hook
 * Manages login, register, logout, and token refresh.
 */
import { useCallback, useEffect } from 'react';
import { fetchPersonas, getMe, login, logout, refreshToken, register } from '../api/auth';
import useAppStore from '../stores/appStore';

export function useAuth() {
  const { accessToken, user, setAuth, clearAuth, setAvailablePersonas, setPersona, setError } =
    useAppStore();

  // Attempt silent token refresh on mount (for returning users)
  useEffect(() => {
    if (!accessToken) {
      _silentRefresh();
    }
  }, []);

  async function _silentRefresh() {
    try {
      const data = await refreshToken();
      setAuth(
        { id: data.user_id, username: data.username, current_persona_id: data.current_persona_id },
        data.access_token,
      );
      await _loadPersonas(data.access_token, data.current_persona_id);
    } catch {
      // No valid session — user needs to log in
    }
  }

  async function _loadPersonas(token, currentPersonaId) {
    try {
      const personas = await fetchPersonas(token);
      setAvailablePersonas(personas);
      const current = personas.find((p) => p.id === currentPersonaId);
      if (current) setPersona(current);
    } catch {
      // Non-fatal
    }
  }

  const handleLogin = useCallback(async (email, password) => {
    const data = await login(email, password);
    setAuth(
      { id: data.user_id, username: data.username, current_persona_id: data.current_persona_id },
      data.access_token,
    );
    await _loadPersonas(data.access_token, data.current_persona_id);
    return data;
  }, []);

  const handleRegister = useCallback(async (username, email, password) => {
    const data = await register(username, email, password);
    setAuth(
      { id: data.user_id, username: data.username, current_persona_id: data.current_persona_id },
      data.access_token,
    );
    await _loadPersonas(data.access_token, data.current_persona_id);
    return data;
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      if (accessToken) await logout(accessToken);
    } catch {}
    clearAuth();
  }, [accessToken]);

  return {
    user,
    accessToken,
    isAuthenticated: !!accessToken,
    login: handleLogin,
    register: handleRegister,
    logout: handleLogout,
  };
}
