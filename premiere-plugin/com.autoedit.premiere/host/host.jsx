/**
 * host.jsx — ExtendScript bridge to Premiere Pro internals
 *
 * Functions here are called from main.js via csInterface.evalScript().
 * They run inside Premiere Pro's scripting engine and have access to
 * the full Premiere DOM (app.project, app.project.importFiles, etc).
 */

/**
 * Import an SRT subtitle file into the active Premiere project.
 *
 * @param  {string} srtPath  Absolute path to the .srt file on disk.
 * @return {string}          "SUCCESS" or an error description string.
 */
function importSrtFile(srtPath) {
  try {
    if (!app.project) {
      return "ERROR: No project is open in Premiere Pro. Please open a project first.";
    }

    var srtFile = new File(srtPath);
    if (!srtFile.exists) {
      return "ERROR: SRT file not found at: " + srtPath;
    }

    var success = app.project.importFiles(
      [srtPath],
      true,
      app.project.rootItem,
      false
    );

    return success ? "SUCCESS" : "IMPORT_FAILED";

  } catch (e) {
    return "ERROR: " + e.message;
  }
}

/**
 * Import an FCP7 XML file as a new sequence in the active Premiere project.
 *
 * @param  {string} xmlPath  Absolute path to the .xml file on disk.
 * @return {string}          "SUCCESS" or an error description string.
 */
function importXmlSequence(xmlPath) {
  try {
    if (!app.project) {
      return "ERROR: No project is open in Premiere Pro. Please open a project first.";
    }

    var xmlFile = new File(xmlPath);
    if (!xmlFile.exists) {
      return "ERROR: XML file not found at: " + xmlPath;
    }

    // importFiles(paths, suppressUI, targetBin, importAsNumberedStills)
    var success = app.project.importFiles(
      [xmlPath],
      true,                    // suppressUI — don't show import dialog
      app.project.rootItem,    // import into root bin
      false                    // not numbered stills
    );

    return success ? "SUCCESS" : "IMPORT_FAILED";

  } catch (e) {
    return "ERROR: " + e.message;
  }
}
