function(VARS, element, context) {
  const screen = fp.rt.get_screen();

  // Always return [ts, value] for each requested timestamp
  function Dateplace(values, timestamps) {
    if (timestamps.length === 0) return [];

    if (!values || values.length === 0) {
      return timestamps.map(ts => [ts, ""]);
    }

    const result = [];
    let valueIndex = 0;

    for (let idx = 0; idx < timestamps.length; idx++) {
      const ts = timestamps[idx];

      while (values[valueIndex][0] < ts) {
        if (valueIndex === values.length - 1) {
          // No more source points; fill the rest with blanks
          for (let j = idx; j < timestamps.length; j++) {
            result.push([timestamps[j], ""]);
          }
          return result;
        }
        valueIndex++;
      }

      let r;
      if (valueIndex === 0 && values[valueIndex][0] !== ts) {
        r = "";
      } else if (values[valueIndex][0] === ts) {
        r = values[valueIndex][1];
      } else {
        r = values[valueIndex - 1][1];
      }

      result.push([ts, r]);
    }

    return result;
  }

  context._button_filter = true;

  const fields = [
    ".name",
    ".pattern",
    ".folder",
    ".fp_path",
    "title",
    "input_range",
    "input",
    "model_path",
    "output_range",
    "step",
    "port",
    "host"
  ].join(", ");

  const object_type = "model_control";
  const baseFilter = `and(.pattern=$oid('/root/FP/prototypes/${object_type}/fields'))`;
  const query = `get ${fields} from * where ${baseFilter} format $to_json`;
  const connection = context.get_connection();

  const step_ms = 3600000;
  const n_values = 24;
  let from = +new Date();
  from = Math.floor(from / (3600000 * 24)) * 3600000 * 24 - 3600000 * 4;
  const to = from + step_ms * n_values;
  const timestamps = Array.from({ length: n_values }, (_, i) => from + i * step_ms);

  connection.get(
    query,
    (raw) => {
      // 1) Filter objects
      const data_orig = raw.filter(
        (d) => d[".fp_path"] !== undefined && d["step"] === 3600
      );
      const n_entries = data_orig.length;

      // 2) Prepare the triplicated data rows (gt, forecast, deviation)
      const data = [];
      for (let i = 0; i < n_entries; i++) {
        const base = data_orig[i];
        const a = structuredClone(base);
        const b = structuredClone(base);
        const c = structuredClone(base);

        a["title"] = `${base["title"]} (факт)`;
        b["title"] = `${base["title"]} (прогноз)`;
        c["title"] = `${base["title"]} (|отклонения|, %)`;

        data.push(a, b, c);
      }

      // 3) Collect all archives once
      const perIndex = []; // [{gt, fc}, ...] aligned to i
      const archivesList = [];

      for (let i = 0; i < n_entries; i++) {
        const obj = data_orig[i];

        const archive_gt =
          obj["input"] && obj["input"].length > 0 ? obj["input"][0] : "";
        const archive_forecast =
          obj[".fp_path"] && obj[".fp_path"].length > 0
            ? obj[".fp_path"] + "/archives/out_value"
            : "";

        perIndex.push({ gt: archive_gt, fc: archive_forecast });

        if (archive_gt && archive_gt !== null && archive_gt !== undefined) archivesList.push(archive_gt);
        if (archive_forecast && archive_forecast !== null && archive_forecast !== undefined) archivesList.push(archive_forecast);
      }

      // Deduplicate archives to minimize backend work
      const uniqueArchives = Array.from(new Set(archivesList));
      console.log(uniqueArchives);

      // 4) Single batched read_archives call
      connection.application(
        "fp_json",
        "read_archives",
        {
          archives: uniqueArchives,
          from,
          to
        },
        (response) => {
          // 5) Post-process the response for every object
          for (let i = 0; i < n_entries; i++) {
            const { gt: archive_gt, fc: archive_forecast } = perIndex[i];

            let values_gt = (response[archive_gt] || []).map(
              ([ts, value]) => [ts, value === null ? "" : value]
            );
            let values_fc = (response[archive_forecast] || []).map(
              ([ts, value]) => [ts, value === null ? "" : value]
            );

            values_gt = Dateplace(values_gt, timestamps);
            values_fc = Dateplace(values_fc, timestamps);

            // Fill GT (index 3*i + 0) and Forecast (index 3*i + 1)
            for (let j = 0; j < 2; j++) {
              let sum = 0.0;
              let count = 0;
              const index = j === 0 ? 3 * i + 0 : 3 * i + 1;
              const values = j === 0 ? values_gt : values_fc;

              if (values.length > 0) {
                for (let k = 0; k < n_values; k++) {
                  const [ts, val] = values[k];
                  if (val !== "") {
                    data[index]["value_" + k] = [ts, val];
                    sum += val;
                    count += 1;
                  } else {
                    data[index]["value_" + k] = [ts, ""];
                  }
                }
                data[index]["mean"] = count > 0 ? (sum / count).toFixed(1) : "";
              }
            }

            // Fill Deviation % (index 3*i + 2)
            {
              let sum = 0.0;
              let count = 0;

              for (let k = 0; k < n_values; k++) {
                const [ts_gt, val_gt] = values_gt[k] || [timestamps[k], ""];
                const [, val_fc] = values_fc[k] || [timestamps[k], ""];

                if (val_gt !== "" && val_fc !== "") {
                  if (Math.abs(val_gt) > 0) {
                    const val =
                      (Math.abs(val_gt - val_fc) / Math.abs(val_gt)) * 100.0;
                    data[3 * i + 2]["value_" + k] = [ts_gt, val];
                    sum += val;
                    count += 1;
                  } else {
                    data[3 * i + 2]["value_" + k] = [ts_gt, ""];
                  }
                } else {
                  data[3 * i + 2]["value_" + k] = [ts_gt, ""];
                }
              }

              data[3 * i + 2]["mean"] = count > 0 ? (sum / count).toFixed(1) : "";
            }
          }

          // 6) Footer + render once
          const [Footer] = screen.find_by_name("footer");
          const From = fp_dev.datetimeToString(timestamps[0]);
          const To = fp_dev.datetimeToString(timestamps[timestamps.length - 1]);
          const FooterText = `Данные выгружены с ${From} по ${To}`;
          Footer.set({ text: FooterText });

          element.set({ data });
        },
        (error) => {
          console.error("read_archives (batched) error:", error);
        }
      );
    },
    console.error
  );
}
