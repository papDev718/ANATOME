import jsPDF from "jspdf";

export default function ReportButton({
  patientName,
  patientAge,
  reportDate,
  regions,
  saveReport,
  isSaving,
}) {
  const generatePDF = async () => {
    try {
      // ==========================================
      // Generate and save the report through FastAPI
      // ==========================================

      if (!saveReport) {
        throw new Error("The report-saving function is unavailable.");
      }

      const savedResult = await saveReport();

      const aiReport = savedResult.ai_report;
      const patientId = savedResult.patient_id;

      if (!aiReport) {
        throw new Error("The server did not return an AI-generated report.");
      }

      // ==========================================
      // PDF setup
      // ==========================================

      const doc = new jsPDF({
        orientation: "portrait",
        unit: "mm",
        format: "a4",
      });

      const today = reportDate || new Date().toLocaleDateString();

      let y = 20;

      // Leave room for the footer at the bottom.
      const bottomMargin = 275;

      // ==========================================
      // PDF helper functions
      // ==========================================

      function ensureSpace(requiredHeight = 12) {
        if (y + requiredHeight > bottomMargin) {
          doc.addPage();
          y = 20;
        }
      }

      function addSectionHeading(title) {
        ensureSpace(15);

        doc.setFont("helvetica", "bold");
        doc.setFontSize(14);
        doc.text(title, 20, y);

        doc.setFont("helvetica", "normal");

        y += 10;
      }

      function addSubheading(title) {
        ensureSpace(12);

        doc.setFont("helvetica", "bold");
        doc.setFontSize(12);

        const wrappedTitle = doc.splitTextToSize(title, 160);

        doc.text(wrappedTitle, 25, y);

        y += wrappedTitle.length * 6 + 2;

        doc.setFont("helvetica", "normal");
      }

      function addWrappedText(value, x = 25, maximumWidth = 160) {
        const textValue =
          typeof value === "string" && value.trim()
            ? value.trim()
            : "Not reported";

        doc.setFont("helvetica", "normal");
        doc.setFontSize(10);

        const lines = doc.splitTextToSize(textValue, maximumWidth);

        for (const line of lines) {
          ensureSpace(6);

          doc.text(line, x, y);

          y += 6;
        }

        y += 3;
      }

      function addLabelledText(label, value) {
        ensureSpace(14);

        doc.setFont("helvetica", "bold");
        doc.setFontSize(10);
        doc.text(`${label}:`, 25, y);

        y += 6;

        doc.setFont("helvetica", "normal");

        addWrappedText(value, 30, 155);
      }

      function addBulletList(items) {
        if (!Array.isArray(items) || items.length === 0) {
          addWrappedText("Not reported");
          return;
        }

        for (const item of items) {
          const lines = doc.splitTextToSize(String(item), 150);

          let firstLine = true;

          for (const line of lines) {
            ensureSpace(6);

            doc.setFont("helvetica", "normal");
            doc.setFontSize(10);

            if (firstLine) {
              doc.text("•", 27, y);
            }

            doc.text(line, 33, y);

            y += 6;
            firstLine = false;
          }

          y += 2;
        }

        y += 3;
      }

      function addDivider() {
        ensureSpace(8);

        doc.line(25, y, 185, y);

        y += 8;
      }

      // ==========================================
      // Header
      // ==========================================

      doc.setFont("helvetica", "bold");
      doc.setFontSize(20);

      doc.text(aiReport.report_title || "Clinical Pain Report", 105, y, {
        align: "center",
        maxWidth: 170,
      });

      y += 10;

      doc.setFont("helvetica", "normal");
      doc.setFontSize(11);

      doc.text("Comprehensive Patient-Reported Pain Documentation", 105, y, {
        align: "center",
      });

      y += 15;

      doc.line(20, y, 190, y);

      y += 15;

      // ==========================================
      // 1. Patient Information
      // ==========================================

      addSectionHeading("1. Patient Information");

      addLabelledText("Patient name", patientName?.trim() || "Not provided");

      addLabelledText("Patient ID", patientId || "Not available");

      addLabelledText(
        "Age",
        patientAge !== undefined && patientAge !== null && patientAge !== ""
          ? String(patientAge)
          : "Not provided",
      );

      addLabelledText("Report date", today);

      // ==========================================
      // 2. Pain Assessment
      // ==========================================

      addSectionHeading("2. Pain Assessment");

      // ==========================================
      // Capture the Three.js canvas snapshot
      // ==========================================

      try {
        // The Three.js renderer draws into a <canvas> inside .anatomy-stage__canvas
        const stageHost = document.querySelector(".anatomy-stage__canvas");
        const glCanvas = stageHost?.querySelector("canvas");

        if (glCanvas) {
          // Snapshot the current WebGL frame (preserveDrawingBuffer is not set,
          // so we read the canvas immediately after a render tick).
          await new Promise((resolve) => requestAnimationFrame(resolve));
          const dataUrl = glCanvas.toDataURL("image/png");

          const pdfWidth = 170;
          const imageProperties = doc.getImageProperties(dataUrl);
          let pdfHeight = (imageProperties.height * pdfWidth) / imageProperties.width;
          const maximumImageHeight = 150;
          if (pdfHeight > maximumImageHeight) pdfHeight = maximumImageHeight;

          addSubheading("3D Anatomy View");
          ensureSpace(pdfHeight + 10);
          doc.addImage(dataUrl, "PNG", 20, y, pdfWidth, pdfHeight);
          y += pdfHeight + 10;
        } else {
          addWrappedText("A 3D pain-location image was not available.");
        }
      } catch (error) {
        console.error("Screenshot capture failed:", error);
        addWrappedText("The 3D pain-location image could not be captured.");
      }

      // ==========================================
      // Raw pain-region information
      // ==========================================

      addSubheading("Reported Pain Regions");

      if (!Array.isArray(regions) || regions.length === 0) {
        addWrappedText("No pain regions were recorded.");
      } else {
        regions.forEach(([_spotId, data], index) => {
          const regionName = data.regionName || `Pain Region ${index + 1}`;

          addSubheading(`${index + 1}. ${regionName}`);

          addLabelledText("Pain severity", `${data.severity ?? 5}/10`);

          addLabelledText("Pain type", data.painType || "Not reported");

          addLabelledText("Frequency", data.frequency || "Not reported");

          addLabelledText("Onset date", data.startDate || "Not reported");

          addLabelledText("Patient notes", data.notes || "Not reported");

          addDivider();
        });
      }

      // ==========================================
      // 3. AI Documentation Summary
      // ==========================================

      addSectionHeading("3. Patient-Reported Clinical Summary");

      addSubheading("Patient Experience");

      addWrappedText(aiReport.patient_experience_summary);

      addSubheading("Pain Course");

      addWrappedText(aiReport.pain_course_summary);

      addSubheading("Functional Impact");

      addWrappedText(aiReport.functional_impact_summary);

      addSubheading("Associated Symptoms");

      addWrappedText(aiReport.associated_symptoms_summary);

      // ==========================================
      // 4. Aggravating and relieving factors
      // ==========================================

      addSectionHeading("4. Aggravating and Relieving Factors");

      addSubheading("Reported Aggravating Factors");

      addBulletList(aiReport.aggravating_factors);

      addSubheading("Reported Relieving Factors");

      addBulletList(aiReport.relieving_factors);

      // ==========================================
      // 5. Region-specific AI summaries
      // ==========================================

      addSectionHeading("5. Region-Specific Documentation");

      if (
        !Array.isArray(aiReport.region_summaries) ||
        aiReport.region_summaries.length === 0
      ) {
        addWrappedText("No region summaries were returned.");
      } else {
        aiReport.region_summaries.forEach((region, index) => {
          addSubheading(
            `${index + 1}. ${region.region_name} — ` + `${region.severity}/10`,
          );

          addLabelledText("Pain character", region.pain_character);

          addLabelledText("Frequency", region.frequency);

          addLabelledText("Onset", region.onset);

          addLabelledText(
            "Original patient note",
            region.original_patient_note,
          );

          addLabelledText(
            "Professionally reworded note",
            region.professionally_reworded_note,
          );

          addLabelledText(
            "Clinical documentation summary",
            region.clinical_summary,
          );

          addDivider();
        });
      }

      // ==========================================
      // 6. Clinician review items
      // ==========================================

      addSectionHeading("6. Items for Clinician Review");

      addBulletList(aiReport.clinician_review_items);

      // ==========================================
      // 7. Documentation statement
      // ==========================================

      addSectionHeading("7. Documentation Statement");

      addWrappedText(aiReport.documentation_statement);

      // ==========================================
      // 8. Blank clinician notes section
      // ==========================================

      addSectionHeading("8. Clinician Notes");

      // Keep the description and box together.
      ensureSpace(55);

      doc.setFont("helvetica", "normal");
      doc.setFontSize(10);

      doc.text("Additional clinician observations:", 25, y);

      y += 8;

      doc.rect(25, y, 160, 40);

      y += 45;

      // ==========================================
      // Footer on every page
      // ==========================================

      const totalPages = doc.getNumberOfPages();

      for (let page = 1; page <= totalPages; page += 1) {
        doc.setPage(page);

        doc.setFont("helvetica", "normal");
        doc.setFontSize(9);

        doc.text("Generated by the ANATOME Pain-Intake System", 105, 287, {
          align: "center",
        });

        doc.text(`Page ${page} of ${totalPages}`, 190, 287, {
          align: "right",
        });
      }

      // ==========================================
      // Download PDF
      // ==========================================

      const safePatientName =
        patientName?.trim().replace(/[^a-zA-Z0-9_-]/g, "_") || "Patient";

      doc.save(`Clinical_Pain_Report_${safePatientName}.pdf`);
    } catch (error) {
      console.error("Report generation failed:", error);

      alert(error.message || "The report could not be saved and generated.");
    }
  };

  return (
    <button
      type="button"
      className="btn btn-primary btn-sm"
      onClick={generatePDF}
      disabled={isSaving}
    >
      {isSaving ? "⏳ Generating Report..." : "🖨️ Save & Print Report"}
    </button>
  );
}
