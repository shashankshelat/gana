import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useToast } from '../hooks/useToast';
import MappingEditor from '../components/Common/MappingEditor';
import Modal from '../components/Common/Modal';
import {
  CheckCircle, XCircle, Clock, AlertTriangle, ExternalLink,
  ChevronDown, ChevronRight, Send, Eye, GitBranch
} from 'lucide-react';
import clsx from 'clsx';

interface Approval {
  id: string;
  connector_name: string;
  connector_type: string;
  ocsf_class_uid: number;
  source: string;
  ai_provider?: string;
  ai_model?: string;
  proposed_mapping: Record<string, unknown>;
  current_mapping: Record<string, unknown>;
  ai_explanation?: string;
  status: 'pending' | 'approved' | 'rejected';
  reviewed_by?: string;
  reviewer_note?: string;
  reviewed_at?: string;
  created_by?: string;
  created_at: string;
  unknown_fields?: UnknownField[];
}

interface UnknownField {
  id: string;
  field_name: string;
  field_path: string;
  ai_description: string;
  ai_suggested_ocsf_path: string;
  sample_values: string[];
  status: string;
  github_issue_url?: string;
}

const STATUS_STYLES = {
  pending: 'badge-yellow',
  approved: 'badge-green',
  rejected: 'badge-red',
};

export default function ApprovalsPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const can = useAuthStore(s => s.can);
  const [filter, setFilter] = useState('');
  const [detailId, setDetailId] = useState<string | null>(null);
  const [editedMappings, setEditedMappings] = useState<Record<string, Record<string, unknown>>>({});
  const [reviewNote, setReviewNote] = useState('');
  const [githubToken, setGithubToken] = useState('');
  const [submitFieldId, setSubmitFieldId] = useState<string | null>(null);
  const [submitContext, setSubmitContext] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: approvals = [], isLoading } = useQuery<Approval[]>({
    queryKey: ['approvals', filter],
    queryFn: () => api.get(`/approvals${filter ? `?status=${filter}` : ''}`).then(r => r.data),
    refetchInterval: 15000,
  });

  const { data: detail } = useQuery<Approval>({
    queryKey: ['approval-detail', detailId],
    queryFn: () => api.get(`/approvals/${detailId}`).then(r => r.data),
    enabled: Boolean(detailId),
  });

  const { data: unknownFields = [] } = useQuery<UnknownField[]>({
    queryKey: ['unknown-fields'],
    queryFn: () => api.get('/approvals/unknown-fields/list').then(r => r.data),
    refetchInterval: 15000,
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, action, note, mapping }: { id: string; action: string; note: string; mapping?: Record<string, unknown> }) =>
      api.post(`/approvals/${id}/review`, {
        action,
        reviewer_note: note || null,
        edited_mapping: mapping || null,
      }).then(r => r.data),
    onSuccess: (data: { status?: string; dlq_events_retried?: number }) => {
      qc.invalidateQueries({ queryKey: ['approvals'] });
      qc.invalidateQueries({ queryKey: ['connectors'] });
      qc.invalidateQueries({ queryKey: ['dlq'] });
      if (data?.dlq_events_retried) {
        toast.success(`Mapping applied · ${data.dlq_events_retried} failed events re-queued from the DLQ`);
      }
      setDetailId(null);
      setReviewNote('');
    },
  });

  const submitFieldMutation = useMutation({
    mutationFn: ({ fieldId, token, context }: { fieldId: string; token: string; context: string }) =>
      api.post(`/approvals/unknown-fields/${fieldId}/submit`, {
        github_token: token,
        additional_context: context || null,
      }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['unknown-fields'] });
      setSubmitFieldId(null);
      setGithubToken('');
      setSubmitContext('');
    },
  });

  const ignoreMutation = useMutation({
    mutationFn: (fieldId: string) => api.post(`/approvals/unknown-fields/${fieldId}/ignore`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['unknown-fields'] }),
  });

  const pendingCount = approvals.filter(a => a.status === 'pending').length;
  const pendingFields = unknownFields.filter(f => f.status === 'pending').length;

  const getMappingForApproval = (approval: Approval) =>
    editedMappings[approval.id] || approval.proposed_mapping;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Approvals</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Review AI-generated mappings before they go live
          </p>
        </div>
        <div className="flex gap-3">
          {pendingCount > 0 && (
            <span className="badge badge-yellow px-3 py-1 text-sm">
              {pendingCount} pending
            </span>
          )}
          {pendingFields > 0 && (
            <span className="badge badge-blue px-3 py-1 text-sm">
              {pendingFields} unknown fields
            </span>
          )}
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit">
        {[['', 'All'], ['pending', 'Pending'], ['approved', 'Approved'], ['rejected', 'Rejected']].map(([val, label]) => (
          <button
            key={val}
            onClick={() => setFilter(val)}
            className={clsx(
              'px-4 py-1.5 text-sm font-medium rounded-md transition-colors',
              filter === val
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700'
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Mapping Approvals */}
      <div className="space-y-3">
        <h2 className="font-semibold text-gray-700 dark:text-gray-300 text-sm uppercase tracking-wider">Mapping Proposals</h2>

        {isLoading ? (
          <div className="card h-32 animate-pulse bg-gray-100 dark:bg-gray-800" />
        ) : approvals.length === 0 ? (
          <div className="card p-10 text-center text-gray-400 dark:text-gray-500">
            No approvals {filter ? `with status "${filter}"` : ''}
          </div>
        ) : (
          approvals.map(approval => (
            <div key={approval.id} className="card overflow-hidden">
              <div
                className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
                onClick={() => setExpanded(expanded === approval.id ? null : approval.id)}
              >
                <div className="flex items-center gap-3 min-w-0">
                  {expanded === approval.id
                    ? <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    : <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  }
                  <div className="min-w-0">
                    <p className="font-medium text-gray-900 dark:text-white truncate">
                      {approval.connector_name || approval.connector_type}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className={`badge ${STATUS_STYLES[approval.status]}`}>{approval.status}</span>
                      {approval.source === 'dlq_ai' && <span className="badge badge-red">Fix for DLQ events</span>}
                      {approval.source === 'dlq_auto' && <span className="badge badge-red">Automatic · from failed events</span>}
                      {approval.source === 'samples_ai' && <span className="badge badge-blue">From sample events</span>}
                      {approval.ai_provider && <span className="badge badge-blue">AI: {approval.ai_provider}/{approval.ai_model}</span>}
                      <span className="text-xs text-gray-400">OCSF {approval.ocsf_class_uid}</span>
                      <span className="text-xs text-gray-400">by {approval.created_by}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                  <span className="text-xs text-gray-400">
                    {new Date(approval.created_at).toLocaleDateString()}
                  </span>
                  <button
                    onClick={e => { e.stopPropagation(); setDetailId(approval.id); }}
                    className="btn-ghost text-xs p-1.5"
                  >
                    <Eye className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {expanded === approval.id && (
                <div className="border-t border-gray-100 dark:border-gray-800 p-4 space-y-4">
                  {approval.ai_explanation && (
                    <div className="text-sm text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
                      <p className="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">AI Explanation</p>
                      {approval.ai_explanation}
                    </div>
                  )}

                  <MappingEditor
                    mapping={getMappingForApproval(approval)}
                    onChange={m => setEditedMappings(prev => ({ ...prev, [approval.id]: m }))}
                  />

                  {approval.status === 'pending' && can('approve') && (
                    <div className="flex items-end gap-3 pt-2">
                      <div className="flex-1">
                        <label className="label">Reviewer Note (optional)</label>
                        <input
                          className="input"
                          value={reviewNote}
                          onChange={e => setReviewNote(e.target.value)}
                          placeholder="Add a note..."
                        />
                      </div>
                      <button
                        onClick={() => reviewMutation.mutate({ id: approval.id, action: 'approve', note: reviewNote, mapping: editedMappings[approval.id] })}
                        disabled={reviewMutation.isPending}
                        className="btn-primary"
                      >
                        <CheckCircle className="w-4 h-4" /> Approve
                      </button>
                      <button
                        onClick={() => reviewMutation.mutate({ id: approval.id, action: 'reject', note: reviewNote })}
                        disabled={reviewMutation.isPending}
                        className="btn-danger"
                      >
                        <XCircle className="w-4 h-4" /> Reject
                      </button>
                    </div>
                  )}

                  {approval.status !== 'pending' && (
                    <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      {approval.status === 'approved' ? <CheckCircle className="w-4 h-4 text-green-500" /> : <XCircle className="w-4 h-4 text-red-500" />}
                      {approval.status} by {approval.reviewed_by}
                      {approval.reviewer_note && ` — "${approval.reviewer_note}"`}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Unknown Fields Section */}
      {unknownFields.length > 0 && (
        <div className="space-y-3">
          <h2 className="font-semibold text-gray-700 dark:text-gray-300 text-sm uppercase tracking-wider flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-orange-500" />
            Fields Not in OCSF Schema ({unknownFields.length})
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            These log fields were detected by AI but have no matching OCSF field. Submit them as proposals to the OCSF community on GitHub.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {unknownFields.map(field => (
              <div key={field.id} className={clsx('card p-4', field.status === 'ignored' && 'opacity-50')}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-mono font-medium text-sm text-gray-900 dark:text-white">{field.field_name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">{field.ai_description}</p>
                    {field.ai_suggested_ocsf_path && (
                      <p className="text-xs text-brand-500 mt-1">
                        Suggested: <code className="font-mono">{field.ai_suggested_ocsf_path}</code>
                      </p>
                    )}
                  </div>
                  <span className={clsx('badge flex-shrink-0',
                    field.status === 'submitted' ? 'badge-green' :
                    field.status === 'ignored' ? 'badge-gray' : 'badge-yellow'
                  )}>
                    {field.status}
                  </span>
                </div>

                {field.github_issue_url && (
                  <a
                    href={field.github_issue_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-xs text-brand-500 hover:text-brand-600 mt-2"
                  >
                    <GitBranch className="w-3 h-3" /> View GitHub Issue
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}

                {field.status === 'pending' && can('approve') && (
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={() => setSubmitFieldId(field.id)}
                      className="btn-primary text-xs flex-1 justify-center"
                    >
                      <Send className="w-3 h-3" /> Submit to OCSF
                    </button>
                    <button
                      onClick={() => ignoreMutation.mutate(field.id)}
                      className="btn-secondary text-xs"
                    >
                      Ignore
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Submit to OCSF modal */}
      <Modal
        open={Boolean(submitFieldId)}
        onClose={() => setSubmitFieldId(null)}
        title="Submit Field Proposal to OCSF"
        size="md"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            This will open a GitHub issue on the <code className="font-mono text-xs">ocsf/ocsf-schema</code> repository proposing this field be added to the standard.
          </p>
          <div>
            <label className="label">GitHub Personal Access Token <span className="text-red-500">*</span></label>
            <input
              type="password"
              className="input font-mono text-xs"
              value={githubToken}
              onChange={e => setGithubToken(e.target.value)}
              placeholder="ghp_..."
              autoComplete="new-password"
            />
            <p className="text-xs text-gray-400 mt-1">
              Needs <code className="font-mono">public_repo</code> scope. Token is not stored.
            </p>
          </div>
          <div>
            <label className="label">Additional Context (optional)</label>
            <textarea
              className="input"
              rows={3}
              value={submitContext}
              onChange={e => setSubmitContext(e.target.value)}
              placeholder="Explain why this field should be in OCSF..."
            />
          </div>

          {submitFieldMutation.isError && (
            <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
              {String((submitFieldMutation.error as { message?: string })?.message || 'Submission failed')}
            </div>
          )}

          {submitFieldMutation.isSuccess && (
            <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20 rounded-lg px-3 py-2">
              <CheckCircle className="w-4 h-4" /> Issue created successfully!
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setSubmitFieldId(null)} className="btn-secondary">Cancel</button>
            <button
              onClick={() => submitFieldMutation.mutate({ fieldId: submitFieldId!, token: githubToken, context: submitContext })}
              disabled={!githubToken || submitFieldMutation.isPending}
              className="btn-primary"
            >
              {submitFieldMutation.isPending ? 'Submitting...' : 'Submit GitHub Issue'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
