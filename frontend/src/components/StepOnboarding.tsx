import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, CheckCircle, Loader2, FileText } from "lucide-react";
import GlowButton from "./GlowButton";
import { uploadCv, CvExtractedData } from "@/lib/mockApi";

interface StepOnboardingProps {
  onNext: (data: {
    firstName: string;
    lastName: string;
    phone: string;
    email: string;
    cvFile: File;
    extractionPromise: Promise<CvExtractedData>;
  }) => void;
}

const StepOnboarding = ({ onNext }: StepOnboardingProps) => {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "ready">("idle");
  const [extractionPromise, setExtractionPromise] = useState<Promise<CvExtractedData> | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFile = useCallback((file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["pdf", "docx", "doc"].includes(ext || "")) return;
    setCvFile(file);
    // Fire extraction in background immediately — don't await
    const promise = uploadCv(file);
    setExtractionPromise(promise);
    setUploadStatus("ready");
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  }, [handleFile]);

  // Continue as soon as personal info + file are present — extraction runs in background
  const canContinue = firstName && lastName && phone && email && uploadStatus === "ready";

  return (
    <motion.div
      initial={{ opacity: 0, x: 80 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -80 }}
      transition={{ duration: 0.4 }}
      className="w-full max-w-xl mx-auto"
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="glass-card p-6 sm:p-8 glow-blue"
      >
        <h2 className="text-2xl font-bold text-gradient mb-6">Welcome to AutoApply AI</h2>
        <p className="text-muted-foreground mb-6 text-sm">Fill in your details and upload your CV to get started.</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm text-muted-foreground mb-1">First Name</label>
            <input
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              className="w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition"
              placeholder="John"
            />
          </div>
          <div>
            <label className="block text-sm text-muted-foreground mb-1">Last Name</label>
            <input
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              className="w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition"
              placeholder="Doe"
            />
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm text-muted-foreground mb-1">Phone Number</label>
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition"
            placeholder="+91 98765 43210"
          />
        </div>

        <div className="mb-6">
          <label className="block text-sm text-muted-foreground mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition"
            placeholder="john@example.com"
          />
        </div>

        {/* CV Upload Zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
          onClick={() => {
            if (uploadStatus !== "idle") return;
            const input = document.createElement("input");
            input.type = "file";
            input.accept = ".pdf,.docx,.doc";
            input.onchange = (e: any) => {
              if (e.target.files[0]) handleFile(e.target.files[0]);
            };
            input.click();
          }}
          className={`relative mb-6 border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-300
            ${isDragOver ? "border-primary bg-primary/10 glow-blue" : "border-border hover:border-primary/50 hover:bg-muted/20"}
            ${uploadStatus !== "idle" ? "cursor-default" : ""}`}
        >
          <AnimatePresence mode="wait">
            {uploadStatus === "idle" && (
              <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
                <p className="text-muted-foreground text-sm">Drag & drop your CV here or click to browse</p>
                <p className="text-muted-foreground/60 text-xs mt-1">PDF or DOCX</p>
              </motion.div>
            )}
            {uploadStatus === "ready" && (
              <motion.div key="ready" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                className="flex flex-col items-center gap-2">
                <CheckCircle className="w-10 h-10 text-neon-green" />
                <p className="text-neon-green text-sm font-medium">CV uploaded successfully</p>
                {cvFile && <p className="text-muted-foreground text-xs flex items-center gap-1"><FileText className="w-3 h-3" />{cvFile.name}</p>}
                <span className="flex items-center gap-1 text-xs text-primary/70 mt-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> AI extracting profile in background...
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <GlowButton
          disabled={!canContinue}
          onClick={() => {
            if (canContinue) onNext({ firstName, lastName, phone, email, cvFile: cvFile!, extractionPromise: extractionPromise! });
          }}
          className="w-full"
        >
          Continue →
        </GlowButton>
      </motion.div>
    </motion.div>
  );
};

export default StepOnboarding;
