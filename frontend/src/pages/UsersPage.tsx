import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useToast } from '../hooks/useToast';
import Modal from '../components/Common/Modal';
import { Users, Plus, Pencil, UserCheck, UserX } from 'lucide-react';
import clsx from 'clsx';

interface User { id: string; username: string; email: string; full_name?: string; role: string; is_active: boolean; last_login_at?: string; created_at: string; }

const ROLE_BADGE: Record<string, string> = { admin: 'badge-red', reviewer: 'badge-blue', viewer: 'badge-gray' };

export default function UsersPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [formOpen, setFormOpen] = useState(false);
  const [editUser, setEditUser] = useState<User | null>(null);
  const [form, setForm] = useState({ username: '', email: '', full_name: '', password: '', role: 'viewer' });

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => api.get('/auth/users').then(r => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: () => editUser
      ? api.patch(`/auth/users/${editUser.id}`, form)
      : api.post('/auth/users', form),
    onSuccess: () => {
      toast.success(editUser ? 'User updated' : 'User created');
      setFormOpen(false);
      setEditUser(null);
      qc.invalidateQueries({ queryKey: ['users'] });
    },
    onError: () => toast.error('Failed to save user'),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => api.patch(`/auth/users/${id}`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });

  const openCreate = () => { setEditUser(null); setForm({ username: '', email: '', full_name: '', password: '', role: 'viewer' }); setFormOpen(true); };
  const openEdit = (u: User) => { setEditUser(u); setForm({ username: u.username, email: u.email, full_name: u.full_name || '', password: '', role: u.role }); setFormOpen(true); };

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2"><Users className="w-6 h-6 text-gray-400" /> User Management</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{users.length} users · manage roles and access</p>
        </div>
        <button onClick={openCreate} className="btn-primary"><Plus className="w-4 h-4" /> Add User</button>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? <div className="h-32 animate-pulse" /> : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-800">
              <tr>{['User', 'Role', 'Last Login', 'Status', ''].map(h => <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {users.map(user => (
                <tr key={user.id} className={clsx('hover:bg-gray-50 dark:hover:bg-gray-800/30', !user.is_active && 'opacity-50')}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white">{user.username[0].toUpperCase()}</div>
                      <div>
                        <p className="font-medium text-gray-900 dark:text-white">{user.username}</p>
                        <p className="text-xs text-gray-500">{user.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3"><span className={clsx('badge', ROLE_BADGE[user.role] || 'badge-gray')}>{user.role}</span></td>
                  <td className="px-4 py-3 text-xs text-gray-500">{user.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : 'Never'}</td>
                  <td className="px-4 py-3"><span className={clsx('badge', user.is_active ? 'badge-green' : 'badge-gray')}>{user.is_active ? 'Active' : 'Inactive'}</span></td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button onClick={() => openEdit(user)} className="btn-ghost p-1.5"><Pencil className="w-3.5 h-3.5" /></button>
                      <button onClick={() => toggleMutation.mutate({ id: user.id, is_active: !user.is_active })} className="btn-ghost p-1.5">
                        {user.is_active ? <UserX className="w-3.5 h-3.5 text-red-500" /> : <UserCheck className="w-3.5 h-3.5 text-green-500" />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={editUser ? 'Edit User' : 'New User'} size="sm">
        <div className="space-y-4">
          {!editUser && <div><label className="label">Username *</label><input className="input" value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} /></div>}
          <div><label className="label">Email *</label><input className="input" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} /></div>
          <div><label className="label">Full Name</label><input className="input" value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} /></div>
          <div><label className="label">Password {editUser ? '(leave blank to keep)' : '*'}</label><input className="input" type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} autoComplete="new-password" /></div>
          <div><label className="label">Role</label><select className="input" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}><option value="viewer">Viewer</option><option value="reviewer">Reviewer</option><option value="admin">Admin</option></select></div>
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setFormOpen(false)} className="btn-secondary">Cancel</button>
            <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="btn-primary">{saveMutation.isPending ? 'Saving...' : editUser ? 'Update' : 'Create User'}</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
