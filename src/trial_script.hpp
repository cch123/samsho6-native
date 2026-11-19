#pragma once
#include <istream>
namespace ss6 {
class ContactTrial;
// Replay the same movement commands and attack edges used by the viewer.
// Initial life and position overrides are available for isolated fixtures.
bool readTrialCommand(ContactTrial& trial,std::istream& input);
}
