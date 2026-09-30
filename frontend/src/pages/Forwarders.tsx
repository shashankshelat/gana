import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { forwarderApi } from '../api/client';
import { Forwarder } from '../types';
import ForwarderCard from '../components/Forwarders/ForwarderCard';
import ForwarderForm from '../components/Forwarders/ForwarderForm';
import { Plus, Upload } from 'lucide-react';

export default function Forwarders() {
  const [formOpen, setFormOpen] = useState(false);
  const [editingForwarder, setEditingForwarder] = useState<Forwarder | null>(null);

  const { data: forwarders = [], isLoading } = useQuery<Forwarder[]>({
    queryKey: ['forwarders'],
    queryFn: forwarderApi.list,
    refetchInterval: 15000,
  });

  const handleEdit = (forwarder: Forwarder) => {
    setEditingForwarder(forwarder);
    setFormOpen(true);
  };

  const handleClose = () => {
    setFormOpen(false);
    setEditingForwarder(null);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Forwarders</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {forwarders.length} forwarder{forwarders.length !== 1 ? 's' : ''} configured
          </p>
        </div>
        <button
          onClick={() => { setEditingForwarder(null); setFormOpen(true); }}
          className="btn-primary"
        >
          <Plus className="w-4 h-4" /> Add Forwarder
        </button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="card h-52 animate-pulse bg-gray-100 dark:bg-gray-800" />
          ))}
        </div>
      ) : forwarders.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center mb-4">
            <Upload className="w-7 h-7 text-gray-400" />
          </div>
          <p className="text-lg font-medium text-gray-900 dark:text-white">No forwarders yet</p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Add a Splunk, Databricks, or Elasticsearch destination
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {forwarders.map(forwarder => (
            <ForwarderCard key={forwarder.id} forwarder={forwarder} onEdit={handleEdit} />
          ))}
        </div>
      )}

      <ForwarderForm open={formOpen} onClose={handleClose} editingForwarder={editingForwarder} />
    </div>
  );
}
