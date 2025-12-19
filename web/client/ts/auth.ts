/**
 * Authentication state management for FlyFun web app.
 * Uses Zustand for state management and JWT cookies for authentication.
 */

import { create } from 'zustand';

// User type from OAuth providers
export interface User {
    email: string;
    name: string | null;
    picture: string | null;
    provider: 'google' | 'apple';
}

// Auth status response from API
interface AuthStatus {
    authenticated: boolean;
    user: User | null;
    providers: {
        google: boolean;
        apple: boolean;
    };
}

// Auth store state and actions
interface AuthState {
    user: User | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    availableProviders: { google: boolean; apple: boolean };

    // Actions
    checkAuth: () => Promise<void>;
    login: (provider: 'google' | 'apple') => void;
    logout: () => Promise<void>;
}

// Create the auth store
export const useAuthStore = create<AuthState>((set, get) => ({
    user: null,
    isLoading: true,
    isAuthenticated: false,
    availableProviders: { google: false, apple: false },

    checkAuth: async () => {
        try {
            set({ isLoading: true });
            const response = await fetch('/api/auth/status');

            if (!response.ok) {
                throw new Error('Failed to check auth status');
            }

            const data: AuthStatus = await response.json();

            set({
                user: data.user,
                isAuthenticated: data.authenticated,
                availableProviders: data.providers,
                isLoading: false
            });
        } catch (error) {
            console.error('Auth check failed:', error);
            set({
                user: null,
                isAuthenticated: false,
                isLoading: false
            });
        }
    },

    login: (provider: 'google' | 'apple') => {
        // Redirect to OAuth flow
        window.location.href = `/api/auth/${provider}`;
    },

    logout: async () => {
        try {
            const response = await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'include'
            });

            if (response.ok) {
                set({
                    user: null,
                    isAuthenticated: false
                });
                // Optionally redirect to login
                // window.location.href = '/login.html';
            }
        } catch (error) {
            console.error('Logout failed:', error);
        }
    }
}));

// Helper function to get user initials for avatar
export function getUserInitials(user: User | null): string {
    if (!user?.name) return '?';
    const names = user.name.split(' ');
    if (names.length >= 2) {
        return `${names[0][0]}${names[names.length - 1][0]}`.toUpperCase();
    }
    return names[0][0].toUpperCase();
}

// Helper function to check if auth is required
export function requireAuth(): boolean {
    const { isAuthenticated, isLoading } = useAuthStore.getState();

    if (isLoading) {
        return false; // Still loading, don't redirect yet
    }

    if (!isAuthenticated) {
        window.location.href = '/login.html';
        return false;
    }

    return true;
}
