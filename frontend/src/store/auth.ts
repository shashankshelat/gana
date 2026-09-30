import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '../api/client';

interface User {
  id: string;
  username: string;
  email: string;
  full_name?: string;
  role: 'admin' | 'reviewer' | 'viewer';
  is_active: boolean;
  last_login_at?: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: () => boolean;
  can: (action: 'approve' | 'manage_users' | 'write') => boolean;
}

function tokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' && payload.exp * 1000 <= Date.now();
  } catch {
    return true;
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,

      login: async (username, password) => {
        const form = new URLSearchParams();
        form.append('username', username);
        form.append('password', password);
        const resp = await api.post('/auth/login', form, {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        });
        const { access_token, user } = resp.data;
        api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
        set({ token: access_token, user });
      },

      logout: () => {
        delete api.defaults.headers.common['Authorization'];
        set({ token: null, user: null });
      },

      isAuthenticated: () => Boolean(get().token && get().user),

      can: (action) => {
        const role = get().user?.role;
        if (!role) return false;
        if (action === 'manage_users') return role === 'admin';
        if (action === 'approve') return role === 'admin' || role === 'reviewer';
        if (action === 'write') return role === 'admin' || role === 'reviewer';
        return true;
      },
    }),
    {
      name: 'ocsf-auth',
      onRehydrateStorage: () => (state) => {
        if (state?.token && tokenExpired(state.token)) {
          // Saved token has expired; drop it so the app sends the user to login instead of showing empty pages
          state.logout();
          return;
        }
        if (state?.token) {
          api.defaults.headers.common['Authorization'] = `Bearer ${state.token}`;
        }
      },
    }
  )
);

// Any 401 means the session is gone (expired token, secret rotated, user disabled): log out and go to login
api.interceptors.response.use(
  response => response,
  error => {
    const url: string = error.config?.url ?? '';
    if (error.response?.status === 401 && !url.includes('/auth/login')) {
      useAuthStore.getState().logout();
      if (window.location.pathname !== '/login') {
        window.location.assign('/login?expired=1');
      }
    }
    return Promise.reject(error);
  },
);
