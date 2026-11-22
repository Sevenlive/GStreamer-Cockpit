import React, { useState } from "react";
import { X } from "lucide-react";

interface NewChannelModalProps {
  onClose: () => void;
  onCreate: (payload: { name: string; description: string; preset: string }) => Promise<void>;
}

const PRESETS = [
  {
    id: "test_record",
    title: "Test Pattern + MP4 Record",
    desc: "SMPTE color bars -> Text & Timecode -> Browser Preview + MP4 file recording.",
  },
  {
    id: "rtsp_rtmp",
    title: "RTSP Ingest -> RTMP Push",
    desc: "IP camera RTSP ingest -> 1080p30 Scale -> YouTube/RTMP push + Preview.",
  },
  {
    id: "pip_switcher",
    title: "Dual-Source PiP Compositor",
    desc: "Main + PiP video sources -> Compositor -> SRT output + Preview.",
  },
  {
    id: "blank",
    title: "Blank Virtual Channel",
    desc: "Empty canvas to build a custom Input -> Transform -> Output graph.",
  },
];

export const NewChannelModal: React.FC<NewChannelModalProps> = ({
  onClose,
  onCreate,
}) => {
  const [name, setName] = useState("CH-04 • Live Production");
  const [description, setDescription] = useState("");
  const [preset, setPreset] = useState("test_record");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("Channel name is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onCreate({ name: name.trim(), description: description.trim(), preset });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create channel.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="new-ch-title">
      <form className="modal-card" onSubmit={handleSubmit}>
        <div className="modal-header">
          <h3 id="new-ch-title">Create Virtual Channel</h3>
          <button type="button" className="btn btn-icon btn-sm" onClick={onClose} aria-label="Close">
            <X size={15} />
          </button>
        </div>

        <div className="modal-body">
          <div className="form-field">
            <label className="form-label" htmlFor="new-ch-name">
              Channel Name
            </label>
            <input
              id="new-ch-name"
              className="form-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. CH-04 • Studio Main"
              autoFocus
            />
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="new-ch-desc">
              Description (optional)
            </label>
            <input
              id="new-ch-desc"
              className="form-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Short description of routing purpose"
            />
          </div>

          <div className="form-field">
            <span className="form-label">Starting Template</span>
            <div className="preset-grid">
              {PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`preset-card ${preset === p.id ? "selected" : ""}`}
                  onClick={() => setPreset(p.id)}
                >
                  <div className="preset-title">{p.title}</div>
                  <div className="preset-desc">{p.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {error && <div className="validation-banner">{error}</div>}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Creating..." : "Create Channel"}
          </button>
        </div>
      </form>
    </div>
  );
};
